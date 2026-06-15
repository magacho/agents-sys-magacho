"""
Environment check for marketplace-price-compare.

Verifies prerequisites and warns loudly if the host looks like a datacenter /
cloud IP — running there will get blocked regardless of stealth quality.
"""

from __future__ import annotations

import os
import sys
import shutil
import json
import urllib.request

# Candidate system browsers when Playwright's bundled Chromium is unavailable.
SYSTEM_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium",
                   "chromium-browser", "microsoft-edge", "microsoft-edge-stable")


def _ok(msg): print(f"  [ok]   {msg}")
def _warn(msg): print(f"  [warn] {msg}")
def _fail(msg): print(f"  [FAIL] {msg}")


def check_python() -> bool:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    _fail(f"Python {v.major}.{v.minor} — need >= 3.10")
    return False


def check_playwright() -> bool:
    try:
        import playwright  # noqa
        _ok("playwright installed")
    except Exception:
        _fail("playwright missing  ->  pip install playwright")
        return False

    # A configured system-browser override satisfies the browser requirement
    # without the bundled Chromium (see browser.py CHROME_* env vars).
    path_override = os.environ.get("MPC_CHROME_PATH")
    if path_override:
        if os.path.exists(path_override):
            _ok(f"using system browser via MPC_CHROME_PATH={path_override}")
            return True
        _fail(f"MPC_CHROME_PATH is set but the file does not exist: {path_override}")
        return False
    channel = os.environ.get("MPC_CHROME_CHANNEL")
    if channel:
        _ok(f"using system browser channel '{channel}' (MPC_CHROME_CHANNEL)")
        return True

    # Otherwise require Playwright's bundled Chromium.
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and os.path.exists(path):
                _ok("chromium build present")
                return True
    except Exception as e:
        _warn(f"could not verify chromium build ({e}); "
              "if launch fails run: python -m playwright install chromium")
        return True

    # Bundled Chromium missing — point at a system browser if one exists, since
    # `playwright install chromium` may not have a build for very new OSes.
    found = next((b for b in SYSTEM_BROWSERS if shutil.which(b)), None)
    if found:
        _warn("bundled chromium not installed, but found system browser "
              f"'{found}' at {shutil.which(found)}.\n"
              "         Use it by exporting one of:\n"
              "           export MPC_CHROME_CHANNEL=chrome\n"
              f"           export MPC_CHROME_PATH={shutil.which(found)}\n"
              "         (or install the bundled build: python -m playwright install chromium)")
        return False
    _fail("chromium not installed  ->  python -m playwright install chromium")
    return False


def check_stealth() -> bool:
    try:
        import playwright_stealth  # noqa
        _ok("playwright-stealth installed")
        return True
    except Exception:
        _warn("playwright-stealth missing (skill still runs with a minimal "
              "fallback patch, but install is recommended)  ->  pip install playwright-stealth")
        return True


def check_ip() -> bool:
    """
    Heuristic: residential IP good, datacenter/hosting bad. Best-effort only.
    """
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=6) as r:
            data = json.load(r)
        org = (data.get("org") or "").lower()
        hosting_flags = ("amazon", "aws", "google", "gcp", "microsoft", "azure",
                         "digitalocean", "ovh", "hetzner", "linode", "vultr",
                         "oracle", "hosting", "datacenter", "data center")
        loc = f"{data.get('city','?')}, {data.get('region','?')}, {data.get('country','?')}"
        if any(f in org for f in hosting_flags):
            _fail(f"host IP looks like a DATACENTER ({data.get('org')}) at {loc}. "
                  "This skill must run on the user's own residential machine/network "
                  "or it WILL be blocked. Stop and tell the user.")
            return False
        _ok(f"IP looks residential ({data.get('org','?')}) at {loc}")
        return True
    except Exception as e:
        _warn(f"could not verify IP type ({e}); ensure you are NOT on cloud/datacenter")
        return True


def main() -> int:
    print("marketplace-price-compare — environment check\n")
    results = [check_python(), check_playwright(), check_stealth(), check_ip()]
    print()
    if all(results):
        print("All good. Run setup_session.py next (one login per marketplace).")
        return 0
    print("One or more checks failed/ warned — see above before running searches.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
