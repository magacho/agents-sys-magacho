"""
Shared browser layer for marketplace-price-compare.

Launches a Chromium with a PERSISTENT profile (so the user's login survives
across runs and the session is born on this machine — never transplanted) and
applies stealth patches. Also provides light, human-like interaction helpers.

Design notes:
- Persistent context (user_data_dir) is what makes the session reusable and
  keeps the fingerprint consistent. This is deliberate; do not switch to
  ephemeral contexts or cookie injection.
- Stealth is applied defensively: the stealth library's API has churned across
  versions, so we try a few entry points and degrade gracefully if absent.
  Stealth is the *last* 10-15% — the real protection is residential IP +
  real session + low volume (see references/anti-detection.md).
"""

from __future__ import annotations

import asyncio
import math
import random
from pathlib import Path
from contextlib import asynccontextmanager

from playwright.async_api import async_playwright, Page, BrowserContext

PROFILE_DIR = Path.home() / ".marketplace-price-compare" / "profile"

# A plausible, consistent desktop UA. Keep it stable — randomizing the
# fingerprint per run looks LESS human, not more.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
VIEWPORT = {"width": 1366, "height": 768}
LOCALE = "pt-BR"
TIMEZONE = "America/Sao_Paulo"


def _apply_stealth_sync(obj) -> bool:
    """Best-effort stealth. Returns True if something was applied."""
    try:
        # playwright-stealth >= 2.x
        from playwright_stealth import Stealth  # type: ignore
        # newer API patches at context creation; if we got a page/context here
        # we still try the legacy call below.
        _ = Stealth
    except Exception:
        pass
    return False


async def _apply_stealth(page: Page) -> bool:
    """Apply page-level stealth if a compatible helper is available."""
    # Try legacy function API first.
    try:
        from playwright_stealth import stealth_async  # type: ignore
        await stealth_async(page)
        return True
    except Exception:
        pass
    # Try 2.x object API applied to an existing page, if present.
    try:
        from playwright_stealth import Stealth  # type: ignore
        s = Stealth()
        # Some versions expose apply_stealth_async(page) or similar.
        for meth in ("apply_stealth_async", "apply_async", "_apply_async"):
            fn = getattr(s, meth, None)
            if fn:
                await fn(page)
                return True
    except Exception:
        pass
    # Fallback: patch the most obvious tell ourselves.
    try:
        await page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        return False  # only the bare-minimum patch
    except Exception:
        return False


@asynccontextmanager
async def launch(headless: bool = True):
    """
    Async context manager yielding (context, page) backed by the persistent
    profile. Use headless=False for the interactive login (setup_session).
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=headless,
            user_agent=USER_AGENT,
            viewport=VIEWPORT,
            locale=LOCALE,
            timezone_id=TIMEZONE,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await _apply_stealth(page)
        try:
            yield context, page
        finally:
            await context.close()


# ---------------------------------------------------------------------------
# Human-like interaction helpers (kept LIGHT — low volume is the real mask)
# ---------------------------------------------------------------------------

async def jitter(lo: float = 0.4, hi: float = 1.6) -> None:
    """Variable pause. Regularity is the tell, not speed."""
    await asyncio.sleep(random.uniform(lo, hi))


async def think(lo: float = 1.5, hi: float = 4.0) -> None:
    """Longer 'reading the page' pause, used sparingly between major steps."""
    await asyncio.sleep(random.uniform(lo, hi))


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type with per-keystroke jitter and an occasional micro-pause."""
    await page.click(selector)
    await jitter(0.2, 0.6)
    for ch in text:
        await page.type(selector, ch, delay=random.uniform(60, 180))
        if random.random() < 0.06:
            await asyncio.sleep(random.uniform(0.2, 0.5))


async def _bezier(p0, p1, p2, p3, steps):
    """Cubic Bézier points for a curved cursor path."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
        y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
        pts.append((x, y))
    return pts


async def human_move_click(page: Page, selector: str) -> None:
    """Move the cursor along a curved path to an element, then click."""
    el = await page.query_selector(selector)
    if not el:
        raise RuntimeError(f"element not found for move/click: {selector}")
    box = await el.bounding_box()
    if not box:
        await el.click()
        return
    tx = box["x"] + box["width"] / 2 + random.uniform(-4, 4)
    ty = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
    sx, sy = random.uniform(0, VIEWPORT["width"]), random.uniform(0, VIEWPORT["height"])
    c1 = (sx + (tx - sx) * 0.3 + random.uniform(-60, 60), sy + (ty - sy) * 0.3 + random.uniform(-60, 60))
    c2 = (sx + (tx - sx) * 0.7 + random.uniform(-40, 40), sy + (ty - sy) * 0.7 + random.uniform(-40, 40))
    steps = random.randint(18, 30)
    for (x, y) in await _bezier((sx, sy), c1, c2, (tx, ty), steps):
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.004, 0.014))
    await jitter(0.1, 0.3)
    await page.mouse.click(tx, ty)


async def human_scroll(page: Page, amount: int = 1200) -> None:
    """Scroll in momentum-like chunks with reading pauses."""
    scrolled = 0
    while scrolled < amount:
        step = random.randint(180, 420)
        await page.mouse.wheel(0, step)
        scrolled += step
        await asyncio.sleep(random.uniform(0.15, 0.5))
        if random.random() < 0.15:  # occasional pause to "read"
            await asyncio.sleep(random.uniform(0.6, 1.4))
