"""
Seed the skill's isolated browser profile from your REAL Chrome profile.

This copies the auth-relevant files (cookies, local/session storage, the key
state) from an existing Chrome profile on THIS machine into the skill's profile
(~/.marketplace-price-compare/profile/). After seeding, the skill reuses the
logins you already have — no per-marketplace setup_session needed — while still
running against its own isolated profile, so you never have to close your normal
Chrome and never risk your day-to-day profile.

Why this works (Linux): Chrome encrypts cookies with a key kept in the OS keyring
under "Chrome Safe Storage", which is per-APPLICATION, not per-profile. Cookies
copied between two profiles of the same user/Chrome decrypt fine. (Cross-machine
or cross-user copies do NOT — that's the transplant the skill warns against.)

Run the skill with the system Chrome so it shares that keyring entry:
    export MPC_CHROME_CHANNEL=chrome

Usage:
    python scripts/seed_profile.py                      # from ~/.config/google-chrome, profile "Default"
    python scripts/seed_profile.py --profile "Profile 1"
    python scripts/seed_profile.py --source-dir ~/.config/google-chrome --with-indexeddb
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402  (for PROFILE_DIR — the skill's isolated profile)

# Default source: Google Chrome's user-data-dir on Linux.
DEFAULT_SOURCE_DIR = Path.home() / ".config" / "google-chrome"

# Files/dirs copied by default (auth + the storage sites read tokens from).
# Cookies live at <profile>/Cookies (classic) or <profile>/Network/Cookies (new).
COOKIE_RELPATHS = ["Cookies", "Network/Cookies"]
COOKIE_SIDECARS = ["-wal", "-journal", "-shm"]   # SQLite WAL/journal companions
DIR_RELPATHS = ["Local Storage", "Session Storage"]
ROOT_FILES = ["Local State"]                      # at the user-data-dir root, not the profile
# Deliberately NOT copied: "Login Data"/"Web Data" (saved passwords — not needed
# for sessions, and not ours to move). IndexedDB is opt-in (it's large).


def _copy_file(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _copy_dir(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return True


def seed(source_dir: Path, profile: str, with_indexeddb: bool) -> int:
    src_profile = source_dir / profile
    if not src_profile.is_dir():
        print(f"[FAIL] source profile not found: {src_profile}")
        print("       Pass --source-dir / --profile to point at the right one. "
              "Profiles usually live in ~/.config/google-chrome/ (Default, 'Profile 1', ...).")
        return 1

    dst_dir = B.PROFILE_DIR
    dst_profile = dst_dir / profile
    dst_profile.mkdir(parents=True, exist_ok=True)
    print(f"Seeding skill profile from {src_profile}\n          into {dst_profile}\n")

    copied = []
    skipped = []

    # Cookies (+ SQLite sidecars), whichever location exists.
    for rel in COOKIE_RELPATHS:
        if _copy_file(src_profile / rel, dst_profile / rel):
            copied.append(rel)
            for sc in COOKIE_SIDECARS:
                _copy_file(src_profile / (rel + sc), dst_profile / (rel + sc))

    # Storage directories.
    for rel in DIR_RELPATHS:
        (copied if _copy_dir(src_profile / rel, dst_profile / rel) else skipped).append(rel + "/")

    if with_indexeddb:
        (copied if _copy_dir(src_profile / "IndexedDB", dst_profile / "IndexedDB")
         else skipped).append("IndexedDB/")
    else:
        skipped.append("IndexedDB/ (use --with-indexeddb to include; it's large)")

    # Root-level Local State (encryption key state / profile metadata).
    for rel in ROOT_FILES:
        (copied if _copy_file(source_dir / rel, dst_dir / rel) else skipped).append(rel)

    print("Copied:")
    for c in copied:
        print(f"  [ok]   {c}")
    if skipped:
        print("Skipped / not found:")
        for s in skipped:
            print(f"  [--]   {s}")

    if not any(rel in copied for rel in COOKIE_RELPATHS):
        print("\n[FAIL] No Cookies file was copied — nothing to reuse. Check --source-dir/--profile.")
        return 1

    print("\nDone. Next:")
    print("  export MPC_CHROME_CHANNEL=chrome   # run with system Chrome (shares the keyring key)")
    print("  python scripts/setup_session.py --status   # should show your sites already logged in")
    print("\nNote: if a site shows NOT logged in, its session may not have survived the copy "
          "(or expired) — just run setup_session.py --marketplace <name> for that one.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed the skill profile from your real Chrome profile.")
    ap.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR,
                    help="Chrome user-data-dir (default ~/.config/google-chrome)")
    ap.add_argument("--profile", default="Default",
                    help="profile folder name inside the source dir (default 'Default')")
    ap.add_argument("--with-indexeddb", action="store_true",
                    help="also copy IndexedDB (large; some sites keep auth there)")
    args = ap.parse_args()

    if B.is_chrome_running(args.source_dir):
        print("[warn] Chrome appears to be running. For a clean copy of the Cookies database, "
              "fully QUIT Chrome first, then re-run this. Proceeding anyway, but the copy may "
              "miss the most recent writes.\n")

    return seed(args.source_dir.expanduser(), args.profile, args.with_indexeddb)


if __name__ == "__main__":
    raise SystemExit(main())
