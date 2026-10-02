"""Leverage subscore: debt to equity, interest coverage, liabilities to assets."""

from app.scoring.curves import blend, interpolate
from app.scoring.models import Subscore
from app.scoring.weights import SUBSCORE_WEIGHTS
from app.xbrl.models import MetricSnapshot

_DEBT_TO_EQUITY = [(0.5, 0.0), (1.5, 25.0), (3.0, 60.0), (5.0, 100.0)]
_INTEREST_COVERAGE = [(0.0, 100.0), (1.0, 80.0), (1.5, 60.0), (3.0, 25.0), (8.0, 0.0)]
_LIABILITIES_TO_ASSETS = [(0.4, 0.0), (0.6, 25.0), (0.8, 60.0), (1.0, 100.0)]

# metric_key -> (knots, weight within the subscore). Weights renormalize over
# whichever signals are present.
_SIGNALS: dict[str, tuple[list[tuple[float, float]], float]] = {
    "debt_to_equity": (_DEBT_TO_EQUITY, 0.35),
    "interest_coverage": (_INTEREST_COVERAGE, 0.40),
    "liabilities_to_assets": (_LIABILITIES_TO_ASSETS, 0.25),
}


def compute_leverage_subscore(metrics: list[MetricSnapshot]) -> Subscore:
    """Leverage subscore from XBRL MetricSnapshots. Unavailable when none of
    its signals could be derived."""
    weight = SUBSCORE_WEIGHTS["leverage"]
    by_key = {s.metric_key: s for s in metrics}
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
    if not scored:
        return Subscore(
            key="leverage",
            family="financial_fundamentals",
            score=0.0,
            weight=weight,
            available=False,
            reason_code="missing_input",
            reason=(
                "no leverage ratio could be derived "
                "(missing debt, equity, liabilities or interest data)"
            ),
        )

    score, signals = blend(scored)
    return Subscore(
        key="leverage",
        family="financial_fundamentals",
        score=score,
        weight=weight,
        available=True,
        signals=signals,
    )
