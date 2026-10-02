# Hand-asserted in Phase 1; Phase 2's backtest emits a replacement dict in
# exactly this shape (see ROADMAP.md "Phase 2 - empirical weight validation").

SUBSCORE_WEIGHTS: dict[str, float] = {
    "liquidity": 0.25,
    "leverage": 0.25,
    "litigation_regulatory": 0.20,
    "governance": 0.15,
    "disclosure_change": 0.15,
}

BAND_THRESHOLDS: dict[str, float] = {
    "elevated": 35,
    "high": 60,
    "severe": 80,
}

# Populated in step 4 - critical binary signals that floor `overall`
# regardless of the weighted sum (e.g. going-concern qualification).
OVERRIDE_RULES: list = []
