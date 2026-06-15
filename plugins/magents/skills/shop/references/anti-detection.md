# Anti-detection rationale & tuning

Read this when tuning stealth/pacing or when a marketplace starts blocking.

## The priority order (don't invert it)

1. **Residential IP (≈85% of the result).** Run on the user's own machine/network.
   A stealth browser on a datacenter IP gets blocked anyway. `check_env.py` warns
   if the host looks like cloud/hosting. Behind a home/office NAT is fine — many
   devices sharing one residential IP is normal and expected by the sites.
2. **Real session, born here.** The session is created by the user logging into
   *this skill's persistent profile* (`~/.marketplace-price-compare/profile/`).
   Never inject cookies exported from another device: same IP but a different
   browser fingerprint on the same session is a detectable mismatch.
3. **Consistent fingerprint.** `browser.py` pins a stable UA, viewport, locale and
   timezone. Do NOT randomize these per run — consistency reads as human; churn
   reads as a bot.
4. **Low volume + human pacing.** A few products, occasionally. The scripts insert
   jittered delays and "reading" pauses, and space out site-to-site. This protects
   the shared IP: a behavioral soft-block lands on the IP and would also hit the
   user's normal browsing.
5. **Stealth patches (the last 10-15%).** `playwright-stealth` hides obvious tells
   (`navigator.webdriver`, plugin arrays, WebGL vendor, etc.). Helpful, not a
   silver bullet — the big vendors (DataDome, Akamai, HUMAN, Cloudflare) use ML on
   subtle behavioral/fingerprint signals that stealth alone won't beat.

## Headed vs headless

`search.py` runs headless for convenience. If a site challenges you, switch that
run to headed (visible) — headless has its own detectable signature. The newer
Chromium headless mode is less detectable than the legacy one.

## If a site starts blocking / showing captcha

- Slow down: increase the `think()` ranges in `browser.py` and reduce `--max-per-site`.
- Re-run that marketplace headed; solve the challenge once in the persistent profile
  so the trust cookie is stored.
- Confirm the session is still valid: `setup_session.py --status`.
- Don't escalate into proxy rotation / fingerprint spoofing farms — that's the
  arms race for mass scraping, not personal use, and it makes things worse here.

## Stealth library notes

The `playwright-stealth` API has changed across versions; `browser.py` applies it
defensively and falls back to a minimal `navigator.webdriver` patch if the
installed version's API differs. If you want stronger stealth, alternatives worth
evaluating are `patchright` (patched Playwright) or `camoufox` (hardened Firefox).
Swap them inside `browser.py`'s `_apply_stealth` / `launch` without touching the
rest of the skill.
