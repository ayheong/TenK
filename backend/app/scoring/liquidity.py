"""Liquidity subscore: current ratio, working capital to assets, cash runway."""

from app.scoring.curves import blend, interpolate
from app.scoring.models import Subscore
from app.scoring.weights import SUBSCORE_WEIGHTS
from app.xbrl.models import MetricSnapshot

# (metric, risk) knots. At or above a 2.0 current ratio is comfortable; at or
# below 0.5, current assets cover under half of short-term obligations.
_CURRENT_RATIO = [(0.5, 100.0), (1.0, 55.0), (1.5, 20.0), (2.0, 0.0)]
_WORKING_CAPITAL_TO_ASSETS = [(-0.25, 100.0), (0.0, 60.0), (0.1, 30.0), (0.25, 0.0)]
_CASH_RUNWAY_MONTHS = [
    (0.0, 100.0),
    (6.0, 70.0),
    (12.0, 30.0),
    (18.0, 10.0),
    (24.0, 0.0),
]

# metric_key -> (knots, weight within the subscore). Weights renormalize over
# whichever signals are present.
_SIGNALS: dict[str, tuple[list[tuple[float, float]], float]] = {
    "working_capital_ratio": (_CURRENT_RATIO, 0.5),
    "working_capital_to_assets": (_WORKING_CAPITAL_TO_ASSETS, 0.2),
    "cash_runway_months": (_CASH_RUNWAY_MONTHS, 0.3),
}


def compute_liquidity_subscore(metrics: list[MetricSnapshot]) -> Subscore:
    """Liquidity subscore from XBRL MetricSnapshots. Unavailable when the
    current ratio can't be computed; cash runway is only present for
    companies burning cash, so its absence is not a gap."""
    weight = SUBSCORE_WEIGHTS["liquidity"]
    by_key = {s.metric_key: s for s in metrics}
    if "working_capital_ratio" not in by_key:
        return Subscore(
            key="liquidity",
            family="financial_fundamentals",
            score=0.0,
            weight=weight,
            available=False,
            reason_code="missing_input",
            reason=(
                "working_capital_ratio unavailable "
                "(missing current assets or liabilities)"
            ),
        )

    scored = [
        (
            key,
            by_key[key].value,
            interpolate(by_key[key].value, knots),
            w,
            by_key[key].xbrl_tag,
        )
        for key, (knots, w) in _SIGNALS.items()
        if key in by_key
    ]
    score, signals = blend(scored)
    return Subscore(
        key="liquidity",
        family="financial_fundamentals",
        score=score,
        weight=weight,
        available=True,
        signals=signals,
    )
