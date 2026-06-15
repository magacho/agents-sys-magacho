# Brazilian import-tax rules (Remessa Conforme)

Read this when explaining or adjusting the landed-cost numbers. **Verify before
trusting** — these rules and rates change, and the real charge only appears at
checkout. Treat `tax.py` output as an estimate.

## Who it applies to

- **International / cross-border listings** (AliExpress, amazon.com (US), and
  cross-border items on Shopee/Amazon BR) → import tax applies.
- **National listings** (Mercado Livre, amazon.com.br national sellers, Brazilian
  sellers on Shopee) → NO import tax. Landed cost = price + shipping, because the
  Brazilian shelf price **already embeds** national taxes (ICMS/IPI/PIS/COFINS) —
  adding more would double-count.

### How "imported" is decided (per listing, not just per marketplace)

`selectors.json` carries an `imported_by_default` baseline per marketplace
(AliExpress + `amazon_us` = true; Mercado Livre, Amazon BR, Shopee = false). On
the **mixed** marketplaces (Amazon BR, Shopee) a single result can be national or
cross-border, so `search.py` looks for a `result_imported_marker` badge ("Enviado
do exterior", "Importado", "Internacional", "Encargos de Importação") **on each
result** and flips `imported` on for that listing when found, overriding the
baseline.

### Amazon's two storefronts

- **amazon.com.br** (`amazon`) → national sellers embed BR taxes in the price
  (nothing to add). Cross-border listings are detected per-result as above.
- **amazon.com** (`amazon_us`, USD, off by default — pass it explicitly) → always
  imported. Prices are in USD and converted to BRL for ranking via `--usd-brl`.

### Platform-disclosed import charge (used as-is)

When a listing shows the platform's **own** import charge — Amazon's *Import Fees
Deposit* / "Encargos de Importação" — `search.py` captures it (`result_import_fee`)
and `tax.py` uses that exact number instead of the Remessa Conforme estimate
(`tax_source = platform_disclosed`), since it's what the user is actually billed.
Amazon collects this deposit at checkout and refunds any difference, so treat it as
the best available figure, not our estimate. The Remessa Conforme math below is the
**fallback** for imported listings that disclose nothing
(`tax_source = remessa_conforme_estimate`).

## The two tiers (compliant platforms — Programa Remessa Conforme)

CIF = item price + shipping (+ insurance, usually ~0).

- **CIF up to US$ 50:** Import Tax (Imposto de Importação) = **20%** of CIF.
- **CIF above US$ 50 (up to US$ 3000):** Import Tax = **60%** of CIF, **minus a
  US$ 20 deduction**.

Then **ICMS** (state tax) applies on top, calculated **"por dentro"** (the base
includes the ICMS itself):

```
base = (CIF + ImportTax) / (1 - icms_rate)
ICMS = base * icms_rate
landed_total = CIF + ImportTax + ICMS
```

`tax.py` uses ~17% as the default ICMS and a per-UF table in `ICMS_BY_STATE`
(also approximate — verify). Pass `--state` to `search.py` to pick the rate.

## Why USD matters

The US$50 tier line is in dollars. To decide the tier for a BRL-priced item, pass
`--usd-brl` (BRL per USD) to `search.py`. Without it, `tax.py` defaults to the LOW
tier and says so in the note — which can understate the tax on pricier imports.

## Keeping it current

If the user reports the estimate is off, the likely causes are: (a) tier rates or
the US$ threshold changed, (b) the ICMS rate for their state is different, or
(c) the platform isn't in the compliant program (different treatment). Update the
constants at the top of `tax.py` and the `ICMS_BY_STATE` map. When in doubt, search
for the current "Programa Remessa Conforme" rules before quoting a number.
