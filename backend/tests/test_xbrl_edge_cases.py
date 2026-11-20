"""Edge cases for the deterministic (XBRL) fact path: tag selection, period
matching, comparative-year lookup and ratio derivation."""

from datetime import date

import pytest

from app.edgar.models import FilingRecord
from app.xbrl.derive import derive_ratios
from app.xbrl.extract import (
    extract_metrics_from_facts,
    extract_net_income_yoy_from_facts,
)
from app.xbrl.models import MetricSnapshot

ACCESSION = "0000000001-25-000001"
OTHER_ACCESSION = "0000000001-24-000001"
FYE = "2025-12-31"
PRIOR_FYE = "2024-12-31"


def _filing(fiscal_year_end: str | None = FYE) -> FilingRecord:
    return FilingRecord(
        ticker="TST",
        cik=1,
        accession=ACCESSION,
        filing_date="2026-02-15",
        fiscal_year_end=fiscal_year_end,
        html_url="https://example.com/tst.htm",
        cached_path="data/cache/1/tst.htm",
    )


def _entry(val: float, end: str = FYE, accn: str = ACCESSION, **extra) -> dict:
    return {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": 2025,
        "form": "10-K",
        "filed": "2026-02-15",
        **extra,
    }


def _facts(tag: str, entries: list[dict], unit: str = "USD", taxonomy="us-gaap"):
    return {taxonomy: {tag: {"units": {unit: entries}}}}


def _by_key(snapshots: list[MetricSnapshot]) -> dict[str, MetricSnapshot]:
    return {s.metric_key: s for s in snapshots}


# ---------------------------------------------------------------- extraction


def test_primary_tag_wins_when_both_primary_and_fallback_present() -> None:
    facts = {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [_entry(100.0)]}
            },
            "Revenues": {"units": {"USD": [_entry(999.0)]}},
        }
    }

    revenue = _by_key(extract_metrics_from_facts(facts, _filing()))["revenue"]

    assert revenue.value == 100.0
    assert revenue.xbrl_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_falls_through_when_primary_tag_has_no_row_for_this_filing() -> None:
    """Primary tag exists but only for an older filing; the fallback tag that
    this filing actually used must be picked up."""
    facts = {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "units": {"USD": [_entry(50.0, accn=OTHER_ACCESSION)]}
            },
            "Revenues": {"units": {"USD": [_entry(120.0)]}},
        }
    }

    revenue = _by_key(extract_metrics_from_facts(facts, _filing()))["revenue"]

    assert revenue.value == 120.0
    assert revenue.xbrl_tag == "Revenues"


def test_ignores_facts_from_other_accessions() -> None:
    facts = _facts("NetIncomeLoss", [_entry(10.0, accn=OTHER_ACCESSION)])

    assert extract_metrics_from_facts(facts, _filing()) == []


def test_empty_facts_payload_yields_no_metrics() -> None:
    assert extract_metrics_from_facts({}, _filing()) == []


def test_tag_with_empty_units_is_skipped() -> None:
    facts = {"us-gaap": {"NetIncomeLoss": {"units": {}}}}

    assert extract_metrics_from_facts(facts, _filing()) == []


def test_picks_current_year_end_row_regardless_of_order() -> None:
    """Company Facts lists rows oldest-first or newest-first depending on the
    filer; the fiscal-year-end match must not depend on position."""
    entries = [_entry(200.0), _entry(150.0, end=PRIOR_FYE)]

    for ordered in (entries, list(reversed(entries))):
        facts = _facts("Assets", ordered)
        assets = _by_key(extract_metrics_from_facts(facts, _filing()))
        assert assets["total_assets"].value == 200.0


def test_unknown_fiscal_year_end_falls_back_to_first_accession_row() -> None:
    facts = _facts("Assets", [_entry(200.0), _entry(150.0, end=PRIOR_FYE)])

    assets = _by_key(extract_metrics_from_facts(facts, _filing(None)))

    assert assets["total_assets"].value == 200.0


def test_records_unit_tag_and_provenance() -> None:
    facts = _facts("ResearchAndDevelopmentExpense", [_entry(7.0)])

    rd = _by_key(extract_metrics_from_facts(facts, _filing()))["rd_expense"]

    assert (rd.unit, rd.source, rd.ticker, rd.cik) == ("USD", "company_facts", "TST", 1)
    assert rd.xbrl_tag == "ResearchAndDevelopmentExpense"
    assert rd.filed_at == date(2026, 2, 15)


def test_non_usd_unit_is_preserved() -> None:
    facts = _facts("Revenues", [_entry(5_000.0)], unit="EUR")

    revenue = _by_key(extract_metrics_from_facts(facts, _filing()))["revenue"]

    assert revenue.unit == "EUR"


def test_shares_outstanding_prefers_balance_sheet_over_cover_page() -> None:
    facts = {
        "us-gaap": {
            "CommonStockSharesOutstanding": {"units": {"shares": [_entry(1_000.0)]}}
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "units": {"shares": [_entry(1_050.0, end="2026-02-01")]}
            }
        },
    }

    shares = _by_key(extract_metrics_from_facts(facts, _filing()))
    assert shares["shares_outstanding"].value == 1_000.0
    assert shares["shares_outstanding"].xbrl_tag == "CommonStockSharesOutstanding"


def test_annual_value_chosen_over_quarterly_value_with_same_end_date() -> None:
    """Some 10-Ks tag Q4 (3-month) values with the same period end as the
    full year. The annual duration must win regardless of order."""
    quarter = _entry(30.0, start="2025-10-01")
    annual = _entry(100.0, start="2025-01-01")

    for ordered in ([quarter, annual], [annual, quarter]):
        facts = _facts("NetIncomeLoss", ordered)
        net_income = _by_key(extract_metrics_from_facts(facts, _filing()))
        assert net_income["net_income"].value == 100.0


# ----------------------------------------------------------- net income YoY


def _ni_facts(*entries: dict) -> dict:
    return _facts("NetIncomeLoss", list(entries))


def _yoy(facts: dict) -> MetricSnapshot | None:
    filing = _filing()
    current = extract_metrics_from_facts(facts, filing)
    return extract_net_income_yoy_from_facts(facts, filing, current)


def test_yoy_uses_most_recent_prior_year_not_oldest() -> None:
    facts = _ni_facts(
        _entry(50.0, end="2023-12-31"),
        _entry(80.0, end=PRIOR_FYE),
        _entry(120.0),
    )

    yoy = _yoy(facts)

    assert yoy is not None
    assert yoy.value == pytest.approx(0.5)
    assert yoy.unit == "ratio"
    assert yoy.source == "derived"
    assert yoy.xbrl_tag == "NetIncomeLoss (yoy)"


def test_yoy_decline() -> None:
    yoy = _yoy(_ni_facts(_entry(100.0, end=PRIOR_FYE), _entry(60.0)))

    assert yoy is not None
    assert yoy.value == pytest.approx(-0.4)


def test_yoy_none_when_prior_year_is_zero() -> None:
    assert _yoy(_ni_facts(_entry(0.0, end=PRIOR_FYE), _entry(60.0))) is None


def test_yoy_none_without_fiscal_year_end() -> None:
    facts = _ni_facts(_entry(100.0, end=PRIOR_FYE), _entry(60.0))
    filing = _filing(None)
    current = extract_metrics_from_facts(facts, filing)

    assert extract_net_income_yoy_from_facts(facts, filing, current) is None


def test_yoy_ignores_prior_year_rows_from_other_accessions() -> None:
    facts = _ni_facts(
        _entry(100.0, end=PRIOR_FYE, accn=OTHER_ACCESSION),
        _entry(60.0),
    )

    assert _yoy(facts) is None


def test_yoy_from_loss_to_profit_is_positive() -> None:
    """Going from -10 to +5 is an improvement; dividing by a negative base
    must not flip the sign into a reported 'decline'."""
    yoy = _yoy(_ni_facts(_entry(-10.0, end=PRIOR_FYE), _entry(5.0)))

    assert yoy is not None
    assert yoy.value > 0


def test_yoy_from_smaller_loss_to_larger_loss_is_negative() -> None:
    yoy = _yoy(_ni_facts(_entry(-10.0, end=PRIOR_FYE), _entry(-30.0)))

    assert yoy is not None
    assert yoy.value < 0


# ---------------------------------------------------------------- derivation


def _snap(key: str, value: float, tag: str | None = None) -> MetricSnapshot:
    return MetricSnapshot(
        ticker="TST",
        cik=1,
        fiscal_year=2025,
        metric_key=key,
        value=value,
        unit="USD",
        xbrl_tag=tag or key,
        source="company_facts",
        filed_at=date(2026, 2, 15),
    )


def _derive(*snaps: MetricSnapshot) -> dict[str, MetricSnapshot]:
    return _by_key(derive_ratios(list(snaps)))


def test_no_inputs_derives_nothing() -> None:
    assert derive_ratios([]) == []


def test_gross_margin_and_rd_pct_values() -> None:
    derived = _derive(
        _snap("revenue", 200.0), _snap("gross_profit", 90.0), _snap("rd_expense", 20.0)
    )

    assert derived["gross_margin"].value == pytest.approx(0.45)
    assert derived["rd_pct_revenue"].value == pytest.approx(0.10)


def test_zero_revenue_skips_revenue_ratios() -> None:
    derived = _derive(
        _snap("revenue", 0.0), _snap("gross_profit", 5.0), _snap("rd_expense", 5.0)
    )

    assert not set(derived) & {"gross_margin", "rd_pct_revenue"}


def test_negative_gross_profit_gives_negative_margin() -> None:
    derived = _derive(_snap("revenue", 100.0), _snap("gross_profit", -10.0))

    assert derived["gross_margin"].value == pytest.approx(-0.1)


def test_working_capital_ratio_and_zero_current_liabilities() -> None:
    derived = _derive(_snap("current_assets", 300.0), _snap("current_liabilities", 150.0))
    assert derived["working_capital_ratio"].value == pytest.approx(2.0)

    derived = _derive(
        _snap("current_assets", 300.0),
        _snap("current_liabilities", 0.0),
        _snap("total_assets", 1000.0),
    )
    assert "working_capital_ratio" not in derived
    # Working capital over assets does not divide by liabilities, so it holds.
    assert derived["working_capital_to_assets"].value == pytest.approx(0.3)


def test_negative_working_capital_to_assets() -> None:
    derived = _derive(
        _snap("current_assets", 100.0),
        _snap("current_liabilities", 300.0),
        _snap("total_assets", 1000.0),
    )

    assert derived["working_capital_to_assets"].value == pytest.approx(-0.2)


def test_zero_total_assets_skips_asset_denominated_ratios() -> None:
    derived = _derive(
        _snap("current_assets", 10.0),
        _snap("current_liabilities", 5.0),
        _snap("total_assets", 0.0),
        _snap("total_liabilities", 5.0),
    )

    assert not set(derived) & {"working_capital_to_assets", "liabilities_to_assets"}


def test_cash_runway_requires_both_cash_and_negative_operating_cash_flow() -> None:
    assert "cash_runway_months" not in _derive(_snap("operating_cash_flow", -12.0))
    assert "cash_runway_months" not in _derive(_snap("cash_and_equivalents", 50.0))
    assert "cash_runway_months" not in _derive(
        _snap("cash_and_equivalents", 50.0), _snap("operating_cash_flow", 0.0)
    )


def test_cash_runway_with_zero_cash_is_zero_months() -> None:
    derived = _derive(_snap("cash_and_equivalents", 0.0), _snap("operating_cash_flow", -12.0))

    assert derived["cash_runway_months"].value == 0.0


def test_debt_to_equity_skipped_for_zero_equity() -> None:
    derived = _derive(_snap("long_term_debt", 100.0), _snap("stockholders_equity", 0.0))

    assert "debt_to_equity" not in derived


def test_debt_to_equity_needs_long_term_debt() -> None:
    derived = _derive(_snap("short_term_debt", 100.0), _snap("stockholders_equity", 50.0))

    assert "debt_to_equity" not in derived


def test_debt_to_equity_adds_each_current_tag_variant_separately() -> None:
    """`LongTermDebt` already contains current maturities, but the
    `LongTermDebtCurrent` tag is also a current-portion tag, so only those
    listed as current portions are excluded from the sum."""
    for tag, expected in [
        ("LongTermDebtCurrent", 2.0),
        ("DebtCurrent", 2.0),
        ("LongTermDebtAndCapitalLeaseObligationsCurrent", 3.0),
        ("ShortTermBorrowings", 3.0),
    ]:
        derived = _derive(
            _snap("long_term_debt", 500.0, "LongTermDebt"),
            _snap("short_term_debt", 100.0, tag),
            _snap("stockholders_equity", 200.0),
        )
        total_debt = 500.0 if expected == 2.0 else 600.0
        assert derived["debt_to_equity"].value == pytest.approx(total_debt / 200.0), tag


def test_noncurrent_long_term_debt_adds_current_portion() -> None:
    derived = _derive(
        _snap("long_term_debt", 400.0, "LongTermDebtNoncurrent"),
        _snap("short_term_debt", 100.0, "LongTermDebtCurrent"),
        _snap("stockholders_equity", 250.0),
    )

    assert derived["debt_to_equity"].value == pytest.approx(2.0)


def test_total_liabilities_not_derived_without_equity() -> None:
    derived = _derive(_snap("total_assets", 1000.0))

    assert not set(derived) & {"total_liabilities", "liabilities_to_assets"}


def test_total_liabilities_derived_with_negative_equity() -> None:
    derived = _derive(_snap("total_assets", 100.0), _snap("stockholders_equity", -50.0))

    assert derived["total_liabilities"].value == pytest.approx(150.0)
    assert derived["liabilities_to_assets"].value == pytest.approx(1.5)


def test_interest_coverage_with_operating_loss_is_negative() -> None:
    derived = _derive(_snap("operating_income", -30.0), _snap("interest_expense", 10.0))

    assert derived["interest_coverage"].value == pytest.approx(-3.0)


def test_interest_coverage_skipped_for_negative_interest_expense() -> None:
    derived = _derive(_snap("operating_income", 30.0), _snap("interest_expense", -10.0))

    assert "interest_coverage" not in derived


def test_derived_snapshots_carry_provenance_from_inputs() -> None:
    derived = _derive(_snap("revenue", 200.0), _snap("gross_profit", 90.0))

    margin = derived["gross_margin"]
    assert margin.source == "derived"
    assert margin.unit == "ratio"
    assert margin.xbrl_tag == "gross_profit/revenue"
    assert (margin.ticker, margin.cik, margin.fiscal_year) == ("TST", 1, 2025)
    assert margin.filed_at == date(2026, 2, 15)


def test_yoy_ignores_quarterly_rows_when_finding_prior_year() -> None:
    """A later-ending Q3 row must not be mistaken for the prior fiscal year."""
    facts = _ni_facts(
        _entry(80.0, end=PRIOR_FYE, start="2024-01-01"),
        _entry(25.0, end="2025-09-30", start="2025-07-01"),
        _entry(120.0, start="2025-01-01"),
    )

    yoy = _yoy(facts)

    assert yoy is not None
    assert yoy.value == pytest.approx(0.5)
