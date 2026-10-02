from datetime import date

import pytest

from app.xbrl.derive import derive_ratios
from app.xbrl.models import MetricSnapshot


def _snap(key: str, value: float) -> MetricSnapshot:
    return MetricSnapshot(
        ticker="X",
        cik=1,
        fiscal_year=2024,
        metric_key=key,
        value=value,
        unit="USD",
        xbrl_tag=key,
        source="company_facts",
        filed_at=date(2025, 1, 1),
    )


def test_balance_sheet_cash_and_leverage_ratios() -> None:
    snapshots = [
        _snap("current_assets", 300.0),
        _snap("current_liabilities", 200.0),
        _snap("total_assets", 1000.0),
        _snap("total_liabilities", 600.0),
        _snap("cash_and_equivalents", 120.0),
        _snap("operating_cash_flow", -60.0),
        _snap("long_term_debt", 400.0),
        _snap("short_term_debt", 100.0),
        _snap("stockholders_equity", 250.0),
        _snap("operating_income", 90.0),
        _snap("interest_expense", 30.0),
    ]

    derived = {s.metric_key: s for s in derive_ratios(snapshots)}

    assert derived["working_capital_to_assets"].value == pytest.approx(0.1)
    assert derived["cash_runway_months"].value == pytest.approx(24.0)
    assert derived["cash_runway_months"].unit == "months"
    assert derived["debt_to_equity"].value == pytest.approx(2.0)
    assert derived["liabilities_to_assets"].value == pytest.approx(0.6)
    assert derived["interest_coverage"].value == pytest.approx(3.0)


def test_debt_to_equity_without_short_term_debt_uses_long_term_only() -> None:
    snapshots = [
        _snap("long_term_debt", 300.0),
        _snap("stockholders_equity", 150.0),
    ]

    derived = {s.metric_key: s for s in derive_ratios(snapshots)}

    assert derived["debt_to_equity"].value == pytest.approx(2.0)


def test_skips_runway_debt_to_equity_and_coverage_when_undefined() -> None:
    snapshots = [
        _snap("cash_and_equivalents", 120.0),
        _snap("operating_cash_flow", 60.0),
        _snap("long_term_debt", 400.0),
        _snap("stockholders_equity", -50.0),
        _snap("operating_income", 90.0),
        _snap("interest_expense", 0.0),
    ]

    keys = {s.metric_key for s in derive_ratios(snapshots)}

    assert not keys & {"cash_runway_months", "debt_to_equity", "interest_coverage"}
