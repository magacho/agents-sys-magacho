"""
Session setup for marketplace-price-compare.

Opens a VISIBLE browser at a marketplace's login page using the persistent
profile, lets the USER log in by hand (password, 2FA, captcha, QR — all done by
the user, never by the skill), then validates that the session is active.

The session is created *in this profile, on this machine* — it is never
imported from elsewhere. That keeps fingerprint + session + IP consistent.

Usage:
    python scripts/setup_session.py --marketplace mercadolivre
    python scripts/setup_session.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B  # noqa: E402

CONFIG = json.loads((Path(__file__).resolve().parent.parent
                     / "config" / "selectors.json").read_text(encoding="utf-8"))
MARKETPLACES = [k for k in CONFIG if not k.startswith("_")]


async def _is_logged_in(page, cfg) -> bool:
    marker = cfg.get("logged_in_marker")
    if not marker:
        return False
    try:
        el = await page.query_selector(marker)
        return el is not None
    except Exception:
        return False


async def setup_one(marketplace: str) -> None:
    cfg = CONFIG[marketplace]
    print(f"\nOpening a visible browser for {marketplace}.")
    print("Log in there by hand (including any 2FA / captcha / QR). "
          "The skill never sees your password.")
    async with B.launch(headless=False) as (context, page):
        await page.goto(cfg["login_url"], wait_until="domcontentloaded")
        print("Waiting for login... (this checks every few seconds; "
              "press Ctrl+C once you're done if it doesn't auto-detect)")
        for _ in range(120):  # up to ~10 minutes
            await asyncio.sleep(5)
            try:
                if await _is_logged_in(page, cfg):
                    print(f"[ok] {marketplace}: session detected and saved to the profile.")
                    await asyncio.sleep(1.5)
                    return
            except Exception:
                pass
        print(f"[warn] {marketplace}: could not auto-detect login within the window. "
              "If you did log in, the session is still saved; run --status to confirm.")


async def status() -> int:
    print("Checking saved sessions (headless)...\n")
    bad = 0
    async with B.launch(headless=True) as (context, page):
        for m in MARKETPLACES:
            cfg = CONFIG[m]
            try:
                await page.goto(cfg["home_url"], wait_until="domcontentloaded", timeout=30000)
                await B.jitter()
                ok = await _is_logged_in(page, cfg)
            except Exception as e:
                ok = False
                print(f"  [err]  {m}: {e}")
                continue
            print(f"  [{'ok' if ok else 'no'}]   {m}: {'logged in' if ok else 'NOT logged in — run setup'}")
            bad += 0 if ok else 1
    print()
    return 0 if bad == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Set up/verify marketplace login sessions.")
    ap.add_argument("--marketplace", choices=MARKETPLACES,
                    help="which marketplace to log into")
    ap.add_argument("--status", action="store_true",
                    help="report which sessions are currently valid")
    args = ap.parse_args()

    if args.status:
        return asyncio.run(status())
    if args.marketplace:
        asyncio.run(setup_one(args.marketplace))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
