# Coarse sector buckets from a filing's SIC code. Only distinctions that change
# how financial metrics should be read are made: a bank has no current/
# non-current split and a REIT or utility is leveraged by design. Everything
# else is "other". SIC is a dated, coarse system, so treat this as a routing
# hint for metric choice, not an investment classification.

from typing import Literal

Sector = Literal[
    "financials", "real_estate", "utilities", "energy", "biotech_pharma", "other"
]

# (low, high, sector), inclusive, first match wins. REITs (6798) and real
# estate (65xx) precede the rest of the finance range, which is 60xx-64xx and
# 67xx (holding/investment offices).
_SIC_RANGES: list[tuple[int, int, Sector]] = [
    (6798, 6798, "real_estate"),
    (6500, 6599, "real_estate"),
    (6000, 6499, "financials"),
    (6700, 6797, "financials"),
    (6799, 6799, "financials"),
    (4900, 4991, "utilities"),
    (1300, 1389, "energy"),
    (2900, 2999, "energy"),
    (2833, 2836, "biotech_pharma"),
    (8731, 8731, "biotech_pharma"),
]


def classify_sector(sic: str | int | None) -> Sector:
    """Map a SIC code to a coarse sector; unknown or malformed codes are
    "other"."""
    try:
        code = int(sic)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "other"
    for low, high, sector in _SIC_RANGES:
        if low <= code <= high:
            return sector
    return "other"
