---
name: marketplace-price-compare
description: Compare the real landed price of a product across AliExpress, Mercado Livre, Shopee and Amazon — including import tax (Remessa Conforme) and shipping — by driving the live sites with a stealth Playwright browser that reuses the user's own logged-in session. Use this skill whenever the user wants to compare prices, find the cheapest option, check shipping (frete) or import tax (imposto/importação) for a product across marketplaces, or asks things like "quanto fica esse produto no AliExpress vs Mercado Livre", "compara preço de X", "qual o custo final com imposto e frete", even if they don't name the marketplaces explicitly. Runs locally (Claude Code, Claude Desktop, Cowork) on the user's own machine/network.
---

# Marketplace Price Compare

Compare the **real cost-to-your-door** of a product across AliExpress, Mercado Livre, Shopee and Amazon. The hard part of this problem is not the comparison — it's reliable data access. This skill solves it by driving the *live* sites with a stealth Playwright browser that reuses the user's **own logged-in session**, then layering a Brazilian import-tax calculator on top so the numbers reflect what the user would actually pay.

Read this whole file before acting. Load `references/` files only when the relevant step needs them.

## Why the architecture is what it is (don't skip)

These four marketplaces sit behind serious anti-bot systems (DataDome, Akamai, PerimeterX/HUMAN, Cloudflare). Three facts shape every decision in this skill:

1. **IP reputation is the dominant signal.** This skill MUST run on the user's own machine / residential IP, never on a cloud or datacenter host. A stealth browser on a datacenter IP gets blocked regardless of how good the stealth is.
2. **The session must be born and live on the machine that automates.** Never copy/transplant cookies from another device — a session created on machine A but driven from machine B has a mismatched browser fingerprint and gets flagged even on the same IP. Instead, log in *from this skill's own persistent browser profile* (see Setup) so fingerprint + session + IP are all consistent.
3. **Low volume is the best behavioral mask.** Personal price comparison is naturally a few products, occasionally — that already looks human. Humanized mouse/typing helps at the margin, but pacing and low frequency do the heavy lifting. Do NOT batch-scrape dozens of items rapidly: a behavioral soft-block lands on the shared IP and would also hit the user's normal browsing.

Full rationale and tuning knobs: `references/anti-detection.md`.

## Environment & prerequisites

Works in Claude Code, Claude Desktop, and Cowork — all run locally with bash + Python. Before the first run, verify dependencies:

```bash
python scripts/check_env.py
```

This checks Python ≥ 3.10, Playwright, the stealth plugin, and that a Chromium build is installed. If anything is missing it prints the exact install commands. Install (one time):

```bash
pip install playwright playwright-stealth
python -m playwright install chromium
```

If `check_env.py` warns that the host looks like a datacenter/cloud IP, STOP and tell the user — this skill will get blocked there and must run on their own machine/network.

## Workflow

### Step 1 — Session setup (one time per marketplace, re-run when expired)

The skill keeps a persistent browser profile at `~/.marketplace-price-compare/profile/` so logins survive across runs. To set up or refresh a session:

```bash
python scripts/setup_session.py --marketplace mercadolivre
```

This opens a **visible** (headed) browser at the marketplace login page using the persistent profile, then waits for the user to finish logging in (including 2FA, captcha, QR — whatever the site asks) and validates the session. The user does the login by hand in that window; the skill never handles passwords. Repeat per marketplace the user cares about (`mercadolivre`, `aliexpress`, `shopee`, `amazon`, and `amazon_us` if comparing the US store). Note that `amazon` (amazon.com.br) and `amazon_us` (amazon.com) are different domains and need separate logins.

Tell the user plainly: a real browser window will open and they need to log in there once. The session then persists.

To check which sessions are currently valid without logging in:

```bash
python scripts/setup_session.py --status
```

### Step 2 — Search and compare

```bash
python scripts/search.py "echo dot 5a geração" \
  --marketplaces mercadolivre,aliexpress,amazon \
  --max-per-site 3 \
  --state SP \
  --usd-brl 5.40
```

`search.py` drives each marketplace's own search box (humanized typing + paced navigation), scrapes the top results, normalizes them, runs the tax/shipping calculation, and prints a table ranked by **landed cost in BRL** plus a JSON blob. `--state` (Brazilian UF, default `SP`) sets the ICMS rate for the import-tax math. `--usd-brl` (BRL per USD) is needed to pick the import-tax tier for BRL items and is **required** to rank `amazon_us` (USD) listings — without it they sort last.

Default marketplaces are Mercado Livre, Amazon (BR), AliExpress and Shopee. **`amazon_us`** (the US storefront, amazon.com, priced in USD) is off by default — add it explicitly when the user wants to compare against importing directly from the US:

```bash
python scripts/search.py "kindle paperwhite" \
  --marketplaces amazon,amazon_us,aliexpress --usd-brl 5.40
```

Present results to the user as a ranked comparison: product title, marketplace, item price, shipping, import tax (only for international listings), and the **total landed cost in BRL**, cheapest first. Make the import-tax source clear — say whether it's the platform's own disclosed charge (reliable) or our Remessa Conforme *estimate* — and link to each listing so the user can verify at checkout.

### Step 3 — Interpret honestly

- **National listings** (Mercado Livre, amazon.com.br national sellers, Shopee Brazilian sellers) have **no import tax** — landed cost = price + shipping. The Brazilian price already embeds national taxes (ICMS/IPI/PIS/COFINS), so nothing is added on top.
- **International listings** are detected **per listing**, not just per marketplace: AliExpress and `amazon_us` are always imported, while on Amazon BR and Shopee a cross-border badge ("Enviado do exterior", "Importado", "Internacional") flips a single result to imported even though the marketplace default is national.
- **Import tax for international listings** comes from one of two sources, shown in the table legend:
  - `*` **platform-disclosed** — the listing shows the platform's own charge (e.g. Amazon's *Import Fees Deposit* / "Encargos de Importação"). Used **as-is**, because it's what the user is actually billed.
  - `~` **Remessa Conforme estimate** — computed by `scripts/tax.py` when nothing is disclosed. This is an *estimate*: the real figure materializes at checkout, and the rules change. See `references/tax-rules.md`.
- **Amazon has two storefronts:** `amazon` = amazon.com.br (national price already includes BR taxes; cross-border items detected per-listing); `amazon_us` = amazon.com (USD, always imported, needs `--usd-brl` to convert to BRL for the ranking).
- The ranking column is **landed cost in BRL**, so USD listings are comparable — but only when `--usd-brl` is supplied; otherwise they show `?(no usd-brl)` and sort last.
- If a marketplace returns no results or the selectors fail, say so explicitly rather than guessing — a stale selector is the most common failure (see below). Never fabricate a price.

## When scraping breaks (it will)

Selectors are the fragile part — these sites change their DOM often. All selectors live in `config/selectors.json`, **not** in the Python code, so they're easy to fix. When `search.py` reports a selector miss for a marketplace:

1. Read `references/selectors.md` for the repair workflow.
2. Open that marketplace's search results in the persistent profile browser, inspect the current DOM, and update the relevant entry in `config/selectors.json`.
3. Re-run the search to confirm.

Do this repair pass yourself when you have browser access — you can load the page and read the live structure. Don't ask the user to hand-edit JSON unless they prefer to.

## Safety & scope rules

- **Local, low-volume, personal use only.** Don't turn this into a bulk scraper or a hosted service — that breaks the IP/behavioral assumptions and the marketplaces' terms, and the consequence (account/IP soft-block) lands on the user.
- **Never handle the user's passwords.** Login happens in the visible browser window, by the user.
- **Never transplant a session** from another device into the profile.
- **Respect pacing.** The scripts insert randomized human delays; don't add flags or loops to defeat them.
- Be transparent that automated access can violate marketplace ToS and that the import-tax number is an estimate.

## File map

- `scripts/check_env.py` — dependency + environment (datacenter-IP) check.
- `scripts/browser.py` — shared: launches the stealth persistent-context browser and provides humanized type/move/scroll helpers. All other scripts import this.
- `scripts/setup_session.py` — opens the visible login browser per marketplace and validates/reports session status.
- `scripts/search.py` — orchestrator: search → scrape → per-listing import detection → tax → ranked-by-BRL output.
- `scripts/tax.py` — Brazilian import-tax (Remessa Conforme) + shipping normalization; also accepts a platform-disclosed import fee (e.g. Amazon Import Fees Deposit) to use as-is. Importable and runnable standalone.
- `config/selectors.json` — per-marketplace selectors, URLs, currency, and the per-listing tax flags (`imported_by_default`, `result_imported_marker`, `result_import_fee`, `in_default`) — the part you edit when a site changes. Includes both `amazon` (amazon.com.br) and `amazon_us` (amazon.com).
- `references/anti-detection.md` — full rationale for IP/session/stealth/pacing and how to tune it.
- `references/tax-rules.md` — current BR import-tax rules, the ICMS "por dentro" math, and a note to verify.
- `references/selectors.md` — how to repair selectors when a site changes its DOM.
