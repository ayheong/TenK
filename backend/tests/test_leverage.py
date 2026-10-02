from datetime import date

import pytest

from app.scoring.leverage import compute_leverage_subscore
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


def test_all_signals_blend() -> None:
    sub = compute_leverage_subscore(
        [
            _metric("debt_to_equity", 1.5),
            _metric("interest_coverage", 3.0),
            _metric("liabilities_to_assets", 0.6),
        ]
    )

    assert sub.available
    assert sub.score == pytest.approx(25.0)
    assert [s.contribution for s in sub.signals] == pytest.approx([8.75, 10.0, 6.25])


def test_negative_coverage_clamps_to_max_risk() -> None:
    sub = compute_leverage_subscore([_metric("interest_coverage", -2.0)])

    assert sub.score == pytest.approx(100.0)


def test_unavailable_without_any_signal() -> None:
    sub = compute_leverage_subscore([])

    assert not sub.available
    assert sub.reason_code == "missing_input"
    assert sub.signals == []


def test_negative_equity_scores_as_maximum_debt_risk() -> None:
    sub = compute_leverage_subscore(
        [_metric("stockholders_equity", -500.0), _metric("interest_coverage", 8.0)]
    )

    assert sub.available
    assert [s.key for s in sub.signals] == ["interest_coverage", "negative_equity"]
    assert sub.score == pytest.approx(100.0 * 0.35 / 0.75)


def test_positive_equity_without_debt_adds_no_negative_equity_signal() -> None:
    sub = compute_leverage_subscore(
        [_metric("stockholders_equity", 500.0), _metric("interest_coverage", 8.0)]
    )

    assert [s.key for s in sub.signals] == ["interest_coverage"]
