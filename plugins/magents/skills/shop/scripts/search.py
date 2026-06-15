"""
Search orchestrator for marketplace-price-compare.

For each requested marketplace: drive its own search, scrape the top results,
normalize price/shipping, compute landed cost (tax.py), then print a ranked
comparison plus a JSON blob. Reuses the persistent logged-in session via
browser.py and paces itself like a human.

Usage:
    python scripts/search.py "echo dot 5" \
        --marketplaces mercadolivre,aliexpress,amazon \
        --max-per-site 3 --state SP --usd-brl 5.4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser as B           # noqa: E402
import tax as T               # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "selectors.json").read_text(encoding="utf-8"))


def parse_brl(int_txt: str, cents_txt: str = "") -> float | None:
    """Parse split price fragments (whole + cents) into a float.

    Works for both BR (R$ 1.234,56) and US ($1,234.56) Amazon layouts because we
    strip every non-digit from the whole part and take the cents fragment as-is.
    """
    if not int_txt:
        return None
    digits = re.sub(r"[^\d]", "", int_txt)
    if not digits:
        return None
    value = float(digits)
    cents = re.sub(r"[^\d]", "", cents_txt or "")
    if cents:
        value += float(cents[:2]) / 100.0
    return value


def parse_money(text: str, currency: str = "BRL") -> float | None:
    """Parse a single money string (e.g. an import-fee line) into a float.

    Currency-aware: BRL uses comma decimals (1.234,56), USD uses dot (1,234.56).
    """
    if not text:
        return None
    m = re.search(r"[\d.,]+", text)
    if not m:
        return None
    s = m.group(0)
    if currency.upper() == "BRL":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


async def _text(el, selector: str) -> str:
    if not selector:
        return ""
    node = await el.query_selector(selector)
    if not node:
        return ""
    try:
        return (await node.inner_text()).strip()
    except Exception:
        return ""


async def _attr(el, selector: str, attr: str) -> str:
    if not selector:
        return ""
    node = await el.query_selector(selector)
    if not node:
        return ""
    try:
        return (await node.get_attribute(attr)) or ""
    except Exception:
        return ""


async def _has(el, selector: str) -> bool:
    """True if any node inside `el` matches `selector` (used for badge detection)."""
    if not selector:
        return False
    try:
        return (await el.query_selector(selector)) is not None
    except Exception:
        return False


async def scrape_marketplace(page, name: str, query: str, max_items: int,
                             state: str, usd_brl: float | None) -> dict:
    cfg = CONFIG[name]
    out = {"marketplace": name, "items": [], "error": None, "selector_miss": False}

    url = cfg["search_url"].format(query=quote(query))
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        out["error"] = f"navigation failed: {e}"
        return out

    await B.think()                      # pause like a human reading results
    await B.human_scroll(page, 900)      # trigger lazy-loaded items

    items = await page.query_selector_all(cfg["result_item"])
    if not items:
        out["selector_miss"] = True
        out["error"] = ("no result items matched 'result_item' — selector likely "
                        "stale; see references/selectors.md to repair "
                        "config/selectors.json")
        return out

    default_imported = bool(cfg.get("imported_by_default", False))
    currency = (cfg.get("currency") or "BRL").upper()
    out["currency"] = currency
    for el in items[: max_items * 2]:    # over-fetch; some rows are ads/empty
        title = await _text(el, cfg["result_title"])
        price = parse_brl(
            await _text(el, cfg["result_price_int"]),
            await _text(el, cfg["result_price_cents"]),
        )
        if not title or price is None:
            continue
        link = await _attr(el, cfg["result_link"], "href")
        if link and link.startswith("/"):
            link = cfg["home_url"].rstrip("/") + link
        free_ship = await el.query_selector(cfg.get("result_shipping_free") or "x-none")
        shipping = 0.0 if free_ship else None   # None = unknown until checkout

        # Per-listing import detection: a cross-border badge on THIS result
        # overrides the marketplace default (Amazon/Shopee are mixed).
        imported = default_imported
        if await _has(el, cfg.get("result_imported_marker") or ""):
            imported = True

        # If the platform discloses its own import charge on the result, capture
        # it and use it as-is instead of the Remessa Conforme estimate.
        known_fee = None
        if imported and cfg.get("result_import_fee"):
            known_fee = parse_money(await _text(el, cfg["result_import_fee"]), currency)

        lc = T.landed_cost(
            price, shipping or 0.0, imported=imported, state=state,
            usd_brl=usd_brl, currency=currency, known_import_fee=known_fee,
        )

        # Comparable ranking key in BRL, regardless of the listing's currency.
        if currency == "BRL":
            landed_brl = lc.total
        elif usd_brl:
            landed_brl = round(lc.total * usd_brl, 2)
        else:
            landed_brl = None   # USD listing but no rate to convert — can't rank fairly

        out["items"].append({
            "title": title[:140],
            "price": price,
            "currency": currency,
            "shipping": shipping,
            "shipping_known": shipping is not None,
            "imported": imported,
            "import_tax": lc.import_tax,
            "icms": lc.icms,
            "tax_source": lc.tax_source,
            "landed_total": lc.total,
            "landed_total_brl": landed_brl,
            "link": link,
            "tax_note": lc.note,
        })
        if len(out["items"]) >= max_items:
            break

    if not out["items"] and not out["error"]:
        out["selector_miss"] = True
        out["error"] = "items found but none parsed (title/price selectors stale)"
    return out


async def run(query: str, marketplaces: list[str], max_items: int,
              state: str, usd_brl: float | None) -> dict:
    results = []
    async with B.launch(headless=True) as (context, page):
        for i, m in enumerate(marketplaces):
            if m not in CONFIG:
                results.append({"marketplace": m, "items": [], "error": "unknown marketplace"})
                continue
            res = await scrape_marketplace(page, m, query, max_items, state, usd_brl)
            results.append(res)
            if i < len(marketplaces) - 1:
                await B.think(3.0, 7.0)   # space out site-to-site like a human
    return {"query": query, "state": state, "results": results}


TAX_SRC_MARK = {
    "national": "",          # price already embeds Brazilian taxes
    "remessa_conforme_estimate": "~",   # our estimate
    "platform_disclosed": "*",          # value disclosed by the platform (e.g. Amazon IFD)
}


def render(report: dict) -> str:
    rows = []
    misses = []
    for r in report["results"]:
        if r.get("error"):
            misses.append(f"  - {r['marketplace']}: {r['error']}")
        for it in r["items"]:
            rows.append((r["marketplace"], it))
    # Rank by BRL-equivalent landed cost; unconvertible USD items sort last.
    rows.sort(key=lambda x: x[1].get("landed_total_brl") if x[1].get("landed_total_brl") is not None else float("inf"))

    lines = [f"\nQuery: {report['query']}   (ICMS state: {report['state']})\n"]
    if not rows:
        lines.append("No results parsed.")
    else:
        lines.append(f"{'#':<3}{'MARKETPLACE':<12}{'PRICE':>12}{'SHIP':>8}"
                     f"{'IMPORT TAX':>13}{'LANDED (BRL)':>14}  TITLE")
        lines.append("-" * 100)
        for i, (mk, it) in enumerate(rows, 1):
            cur = "$" if it.get("currency") == "USD" else "R$"
            price = f"{cur}{it['price']:.2f}"
            ship = "free" if it["shipping"] == 0 else ("?" if not it["shipping_known"] else f"{it['shipping']:.2f}")
            mark = TAX_SRC_MARK.get(it.get("tax_source", ""), "")
            tax = f"{it['import_tax']:.2f}{mark}" if it["imported"] else "-"
            landed_brl = it.get("landed_total_brl")
            landed = f"{landed_brl:.2f}" if landed_brl is not None else "?(no usd-brl)"
            lines.append(
                f"{i:<3}{mk:<12}{price:>12}{ship:>8}"
                f"{tax:>13}{landed:>14}  {it['title'][:38]}"
            )
        lines.append("\nLanded (BRL) = price + shipping + (import tax + ICMS for imported items), converted to BRL.")
        lines.append("Import tax legend:  ~ = Remessa Conforme estimate   * = value disclosed by the platform (e.g. Amazon Import Fees Deposit, used as-is)   - = national listing (taxes already in price).")
        lines.append("Estimated (~) import tax is approximate — the real figure appears at checkout.")
        lines.append("'?' shipping = not free / unknown until checkout. USD listings need --usd-brl to rank.")
    if misses:
        lines.append("\nSelector / fetch issues:")
        lines.extend(misses)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare a product's landed cost across marketplaces.")
    ap.add_argument("query", help="product to search for")
    default_mks = ",".join(
        k for k, v in CONFIG.items()
        if not k.startswith("_") and isinstance(v, dict) and v.get("in_default", True)
    )
    ap.add_argument("--marketplaces", default=default_mks,
                    help="comma list: mercadolivre,amazon,aliexpress,shopee,amazon_us "
                         "(amazon_us = amazon.com / USD, off by default — add it explicitly)")
    ap.add_argument("--max-per-site", type=int, default=3)
    ap.add_argument("--state", default="SP", help="Brazilian UF for ICMS (default SP)")
    ap.add_argument("--usd-brl", type=float, default=None,
                    help="BRL per USD, used to pick the import-tax tier (US$50 line)")
    ap.add_argument("--json", action="store_true", help="print raw JSON only")
    args = ap.parse_args()

    mks = [m.strip() for m in args.marketplaces.split(",") if m.strip()]
    report = asyncio.run(run(args.query, mks, args.max_per_site, args.state, args.usd_brl))

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report))
        print("\n--- JSON ---")
        print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
