from datetime import date

import pytest

from app.scoring.liquidity import compute_liquidity_subscore
from app.xbrl.models import MetricSnapshot


def _metric(key: str, value: float) -> MetricSnapshot:
    return MetricSnapshot(
        ticker="X",
        cik=1,
        fiscal_year=2024,
        metric_key=key,
        value=value,
        unit="ratio",
        xbrl_tag=key,
        source="derived",
        filed_at=date(2025, 1, 1),
    )


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(3.0, 0.0), (2.0, 0.0), (1.5, 20.0), (1.0, 55.0), (0.75, 77.5), (0.2, 100.0)],
)
def test_score_curve(ratio: float, expected: float) -> None:
    sub = compute_liquidity_subscore([_metric("working_capital_ratio", ratio)])
    assert sub.available
    assert sub.score == pytest.approx(expected)
    assert sub.signals[0].contribution == pytest.approx(expected)


def test_unavailable_without_ratio() -> None:
    sub = compute_liquidity_subscore([])
    assert not sub.available
    assert sub.reason_code == "missing_input"
    assert sub.reason
    assert sub.signals == []


def test_signals_blend_with_renormalized_weights() -> None:
    sub = compute_liquidity_subscore(
        [
            _metric("working_capital_ratio", 1.0),
            _metric("cash_runway_months", 6.0),
        ]
    )

    # 55 * 0.5/0.8 + 70 * 0.3/0.8
    assert sub.score == pytest.approx(60.625)
    assert {s.key for s in sub.signals} == {
        "working_capital_ratio",
        "cash_runway_months",
    }
    assert sum(s.contribution for s in sub.signals) == pytest.approx(sub.score)
