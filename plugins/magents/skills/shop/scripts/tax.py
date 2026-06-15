"""
Brazilian landed-cost calculator for marketplace-price-compare.

Computes the *estimated* import tax (Programa Remessa Conforme) on top of an
item price + shipping, including the ICMS "por dentro" (gross-up) calculation.

IMPORTANT: these rules change and rates vary by state. Treat every number as an
ESTIMATE and tell the user the real figure appears at checkout. See
references/tax-rules.md and verify current rules before relying on this.

Default rules encoded here (verify currency before trusting):
  - Compliant-platform import tax (Imposto de Importacao):
      * CIF up to US$ 50 .............. 20%
      * CIF above US$ 50 (to 3000) .... 60% with a US$ 20 deduction
  - ICMS: state-dependent (default 17%), calculated "por dentro":
      base = (CIF + II) / (1 - icms_rate); icms = base * icms_rate
  CIF here = item_price + shipping (+ insurance, usually ~0 for these).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

# Approximate ICMS rates by UF for imports (verify — these move).
ICMS_BY_STATE = {
    "AC": 0.17, "AL": 0.17, "AP": 0.18, "AM": 0.20, "BA": 0.205, "CE": 0.20,
    "DF": 0.20, "ES": 0.17, "GO": 0.19, "MA": 0.22, "MT": 0.17, "MS": 0.17,
    "MG": 0.18, "PA": 0.19, "PB": 0.20, "PR": 0.195, "PE": 0.205, "PI": 0.21,
    "RJ": 0.20, "RN": 0.18, "RO": 0.195, "RR": 0.20, "RS": 0.17, "SC": 0.17,
    "SP": 0.18, "SE": 0.19, "TO": 0.20,
}
DEFAULT_ICMS = 0.17

LOW_TIER_RATE = 0.20      # II for CIF <= threshold
HIGH_TIER_RATE = 0.60     # II for CIF > threshold
HIGH_TIER_DEDUCTION_USD = 20.0
THRESHOLD_USD = 50.0


@dataclass
class LandedCost:
    currency: str
    item_price: float
    shipping: float
    cif: float
    import_tax: float          # Imposto de Importacao (federal)
    icms: float
    icms_rate: float
    total: float
    imported: bool
    state: str
    tax_source: str            # national | remessa_conforme_estimate | platform_disclosed
    note: str

    def as_dict(self):
        return asdict(self)


def icms_rate_for(state: str | None) -> float:
    if not state:
        return DEFAULT_ICMS
    return ICMS_BY_STATE.get(state.upper().strip(), DEFAULT_ICMS)


def landed_cost(
    item_price: float,
    shipping: float = 0.0,
    *,
    imported: bool,
    state: str | None = "SP",
    usd_brl: float | None = None,
    currency: str = "BRL",
    known_import_fee: float | None = None,
) -> LandedCost:
    """
    Compute landed cost.

    For NATIONAL listings (imported=False): total = price + shipping, no tax.
    For IMPORTED listings (imported=True): apply the Remessa Conforme estimate,
    UNLESS `known_import_fee` is given — when the platform itself discloses the
    import charge (e.g. Amazon's Import Fees Deposit), we trust that figure as-is
    instead of estimating, since it's what the user will actually be billed.

    The US$ thresholds are evaluated in USD; if prices are in BRL, pass
    `usd_brl` (BRL per USD) so the CIF can be compared against the US$50 line.
    If usd_brl is None for an imported item, we assume the price is already a
    fair proxy and apply the low tier — and flag it in the note.
    """
    cif = round(item_price + shipping, 2)
    rate = icms_rate_for(state)

    if not imported:
        return LandedCost(
            currency=currency, item_price=item_price, shipping=shipping, cif=cif,
            import_tax=0.0, icms=0.0, icms_rate=0.0, total=cif, imported=False,
            state=(state or "").upper(), tax_source="national",
            note="National listing — no import tax. Total = price + shipping.",
        )

    # Platform already disclosed the import charge (e.g. Amazon Import Fees
    # Deposit) — trust it and skip the estimate. The disclosed value bundles
    # duties + ICMS into one figure, so we don't break it apart.
    if known_import_fee is not None:
        fee = max(round(known_import_fee, 2), 0.0)
        return LandedCost(
            currency=currency, item_price=item_price, shipping=shipping, cif=cif,
            import_tax=fee, icms=0.0, icms_rate=0.0, total=round(cif + fee, 2),
            imported=True, state=(state or "").upper(), tax_source="platform_disclosed",
            note="Import charge disclosed by the platform (e.g. Amazon Import Fees "
                 "Deposit), used as-is — not the Remessa Conforme estimate.",
        )

    # Determine tier using USD if we can convert.
    note = "Estimate (Remessa Conforme). Real value shown at checkout."
    if usd_brl and currency.upper() == "BRL" and usd_brl > 0:
        cif_usd = cif / usd_brl
    elif currency.upper() == "USD":
        cif_usd = cif
    else:
        cif_usd = 0.0  # unknown — default to low tier
        note += " Tier assumed LOW (no USD conversion provided)."

    if cif_usd > THRESHOLD_USD:
        ii = cif * HIGH_TIER_RATE
        # US$20 deduction converted to the working currency when possible.
        if usd_brl and currency.upper() == "BRL":
            ii -= HIGH_TIER_DEDUCTION_USD * usd_brl
        elif currency.upper() == "USD":
            ii -= HIGH_TIER_DEDUCTION_USD
        ii = max(ii, 0.0)
    else:
        ii = cif * LOW_TIER_RATE

    # ICMS "por dentro": base includes the ICMS itself.
    base = (cif + ii) / (1 - rate)
    icms = base * rate
    total = round(cif + ii + icms, 2)

    return LandedCost(
        currency=currency, item_price=item_price, shipping=shipping, cif=cif,
        import_tax=round(ii, 2), icms=round(icms, 2), icms_rate=rate,
        total=total, imported=True, state=(state or "").upper(),
        tax_source="remessa_conforme_estimate", note=note,
    )


if __name__ == "__main__":
    # Quick demo
    import json
    print(json.dumps(landed_cost(120.0, 15.0, imported=True, state="SP",
                                 usd_brl=5.4, currency="BRL").as_dict(),
                      indent=2, ensure_ascii=False))
    print(json.dumps(landed_cost(120.0, 0.0, imported=False, state="SP").as_dict(),
                      indent=2, ensure_ascii=False))
    # Platform-disclosed import fee (e.g. Amazon US Import Fees Deposit), in USD
    print(json.dumps(landed_cost(45.0, 12.0, imported=True, state="SP",
                                 currency="USD", known_import_fee=18.5).as_dict(),
                      indent=2, ensure_ascii=False))
