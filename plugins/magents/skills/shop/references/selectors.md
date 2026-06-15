# Repairing selectors

Selectors are the fragile part of this skill — the four marketplaces change their
DOM frequently. When `search.py` reports `selector_miss` or an empty result for a
marketplace, the fix is almost always in `config/selectors.json`, not in the code.

## Repair workflow

1. Run `setup_session.py --status` to confirm the session for that marketplace is
   still valid. A "logged out" state looks like a selector miss but is a different
   problem — re-run `setup_session.py --marketplace <name>` if needed.

2. Open the live search results in the persistent profile so you see exactly what
   the scraper sees. Quick way:

   ```bash
   python - <<'PY'
   import asyncio, sys; sys.path.insert(0, "scripts")
   import browser as B
   async def main():
       async with B.launch(headless=False) as (ctx, page):
           await page.goto("https://lista.mercadolivre.com.br/echo-dot")
           await asyncio.sleep(60)   # inspect the DOM in DevTools
   asyncio.run(main())
   PY
   ```

3. In DevTools, find stable selectors for: the result container (`result_item`),
   `result_title`, `result_price_int` (and `result_price_cents` if the cents are a
   separate node), `result_link`, and the free-shipping marker. Prefer attributes
   that look semantic and stable (`data-*`, component names) over hashed/random
   class names.

4. Update the marketplace's entry in `config/selectors.json`. You can list
   fallbacks with commas — Playwright treats `"a, b"` as "match a or b".

   Optional per-listing tax fields (see `_per_listing_tax` in the JSON):
   - `result_imported_marker` — selectors that, when matched **inside a single
     result**, mark that listing as cross-border and flip `imported` on for it
     (overriding `imported_by_default`). Use this on mixed marketplaces (Amazon
     BR, Shopee) where some sellers are national and some ship from abroad. Lean
     on `:has-text('Enviado do exterior')`, `:has-text('Importado')`,
     `:has-text('Internacional')` and similar badge text.
   - `result_import_fee` — selector for an import charge the platform shows on the
     result itself (e.g. Amazon's "Encargos de Importação" / "Import Fees
     Deposit"). When matched, `search.py` parses the number and uses it as-is
     instead of the Remessa Conforme estimate. Point it at the node whose text
     contains the fee; `parse_money` extracts the number (currency-aware).
   - `currency` — `"BRL"` (default) or `"USD"` (foreign storefronts like
     `amazon_us`). Drives parsing and the BRL conversion used for ranking.
   - `in_default` — set `false` to keep a marketplace out of the default run set
     (so it's only hit when named explicitly in `--marketplaces`).

5. Re-run the search and confirm rows parse:

   ```bash
   python scripts/search.py "echo dot" --marketplaces mercadolivre --max-per-site 3
   ```

## Tips

- `result_price_int` / `result_price_cents`: many BR sites split the integer and
  cents into separate nodes. If price is one node like "R$ 1.234,56", put it all in
  `result_price_int` and leave `result_price_cents` empty — `parse_brl` handles it.
- Lazy loading: results often load on scroll. `search.py` already scrolls before
  scraping; if a site needs more, raise the scroll amount in `scrape_marketplace`.
- AliExpress/Shopee use heavily obfuscated class names that rotate — lean on
  `[class*='partial']` attribute-contains selectors and `data-*` hooks.
- `amazon` (amazon.com.br) and `amazon_us` (amazon.com) share almost identical
  DOM — when you fix one, check whether the other needs the same change. The US
  storefront prices are in USD and parse the same way (`a-price-whole` +
  `a-price-fraction`); only the thousands/decimal punctuation differs, which
  `parse_brl` already strips.
- Start with Mercado Livre (least hostile, most stable DOM) when validating
  changes, then move to the harder sites.
