"""Multi-year trend metrics: synthetic edge cases plus real-filer regressions."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.edgar.models import FilingRecord
from app.xbrl.extract import extract_all, extract_metrics_from_facts
from app.xbrl.trends import annual_series, derive_trends

FIXTURES = Path(__file__).parent / "fixtures" / "real_filers"
ACCESSION = "0000000001-26-000001"


def _filing(fye: str | None = "2025-12-31", filed: str = "2026-02-15") -> FilingRecord:
    return FilingRecord(
        ticker="TST", cik=1, accession=ACCESSION, filing_date=filed,
        fiscal_year_end=fye, html_url="https://example.com/x.htm", cached_path="x",
    )


def _row(end: str, val: float, *, days: int | None = 364, filed: str | None = None,
         form: str = "10-K", accn: str = ACCESSION) -> dict:
    row = {"end": end, "val": val, "accn": accn, "fy": int(end[:4]), "form": form,
           "filed": filed or f"{int(end[:4]) + 1}-02-15"}
    if days is not None:
        start = date.fromisoformat(end).toordinal() - days
        row["start"] = date.fromordinal(start).isoformat()
    return row


def _facts(**tags: list[dict]) -> dict:
    return {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}


def _trends(facts: dict, filing: FilingRecord | None = None) -> dict:
    filing = filing or _filing()
    current = extract_metrics_from_facts(facts, filing)
    return {m.metric_key: m for m in derive_trends(facts, filing, current)}


def _revenue(*pairs: tuple[str, float], **kw) -> dict:
    return _facts(Revenues=[_row(end, val, **kw) for end, val in pairs])


# ------------------------------------------------------------- revenue trends


def test_revenue_yoy_and_three_year_cagr() -> None:
    trends = _trends(_revenue(
        ("2022-12-31", 100.0), ("2023-12-31", 110.0),
        ("2024-12-31", 121.0), ("2025-12-31", 133.1),
    ))

    assert trends["revenue_yoy_pct"].value == pytest.approx(0.10)
    assert trends["revenue_cagr_3y"].value == pytest.approx(0.10)
    assert trends["revenue_cagr_3y"].unit == "ratio"
    assert trends["revenue_cagr_3y"].source == "derived"


def test_declining_revenue_gives_negative_trend() -> None:
    trends = _trends(_revenue(
        ("2022-12-31", 200.0), ("2024-12-31", 120.0), ("2025-12-31", 100.0),
        ("2023-12-31", 160.0),
    ))

    assert trends["revenue_yoy_pct"].value == pytest.approx(-20 / 120)
    assert trends["revenue_cagr_3y"].value < 0


def test_two_years_of_history_gives_yoy_but_no_cagr() -> None:
    trends = _trends(_revenue(("2024-12-31", 100.0), ("2025-12-31", 150.0)))

    assert trends["revenue_yoy_pct"].value == pytest.approx(0.5)
    assert "revenue_cagr_3y" not in trends


def test_single_year_of_history_gives_no_trends() -> None:
    assert _trends(_revenue(("2025-12-31", 100.0))) == {}


def test_a_gap_in_history_is_not_bridged_by_the_nearest_row() -> None:
    """With no fiscal year near three years back, the CAGR must be skipped
    instead of silently stretching over four or five years."""
    trends = _trends(_revenue(("2020-12-31", 50.0), ("2024-12-31", 100.0),
                              ("2025-12-31", 110.0)))

    assert "revenue_cagr_3y" not in trends
    assert trends["revenue_yoy_pct"].value == pytest.approx(0.10)


def test_cagr_skipped_when_a_year_is_not_positive() -> None:
    trends = _trends(_revenue(("2022-12-31", 0.0), ("2024-12-31", 50.0),
                              ("2025-12-31", 100.0)))

    assert "revenue_cagr_3y" not in trends
    assert trends["revenue_yoy_pct"].value == pytest.approx(1.0)


def test_quarterly_rows_do_not_pollute_the_annual_series() -> None:
    rows = [
        _row("2024-12-31", 100.0), _row("2025-12-31", 120.0),
        _row("2025-12-31", 35.0, days=90),
        _row("2025-09-30", 30.0, days=90),
    ]

    series, _ = annual_series(_facts(Revenues=rows), "revenue", _filing())

    assert series == [(date(2024, 12, 31), 100.0), (date(2025, 12, 31), 120.0)]


def test_restated_period_uses_the_latest_filed_value() -> None:
    rows = [
        _row("2024-12-31", 100.0, filed="2025-02-15"),
        _row("2024-12-31", 90.0, filed="2026-02-15"),  # restated in the next 10-K
        _row("2025-12-31", 99.0),
    ]

    trends = _trends(_facts(Revenues=rows))

    assert trends["revenue_yoy_pct"].value == pytest.approx(0.10)


def test_filings_made_after_the_analyzed_filing_are_ignored() -> None:
    """Analyzing FY2024 must not see FY2025 data filed later."""
    filing = _filing(fye="2024-12-31", filed="2025-02-15")
    facts = _revenue(("2023-12-31", 100.0), ("2024-12-31", 110.0),
                     ("2025-12-31", 500.0))

    trends = _trends(facts, filing)

    assert trends["revenue_yoy_pct"].value == pytest.approx(0.10)


def test_non_annual_forms_are_ignored() -> None:
    rows = [_row("2024-12-31", 100.0, form="10-Q"), _row("2025-12-31", 150.0)]

    assert _trends(_facts(Revenues=rows)) == {}


def test_tag_that_stopped_reporting_never_supplies_the_current_year() -> None:
    """The contract-revenue tag is first in the fallback list but ended years
    ago; the trend must come from the tag the company still reports."""
    facts = _facts(
        RevenueFromContractWithCustomerExcludingAssessedTax=[
            _row("2021-12-31", 999.0), _row("2022-12-31", 999.0)],
        Revenues=[_row("2024-12-31", 100.0), _row("2025-12-31", 110.0)],
    )

    trends = _trends(facts)

    assert trends["revenue_yoy_pct"].value == pytest.approx(0.10)
    assert trends["revenue_yoy_pct"].xbrl_tag == "Revenues (yoy)"


def test_no_current_metrics_means_no_trends() -> None:
    assert derive_trends({}, _filing(), []) == []


# ---------------------------------------------------------- margin and others


def test_gross_margin_change_over_three_years() -> None:
    facts = _facts(
        Revenues=[_row("2022-12-31", 100.0), _row("2025-12-31", 200.0)],
        GrossProfit=[_row("2022-12-31", 50.0), _row("2025-12-31", 80.0)],
    )

    trends = _trends(facts)

    assert trends["gross_margin_change_3y"].value == pytest.approx(0.40 - 0.50)


def test_gross_margin_change_needs_matching_years_for_both_series() -> None:
    facts = _facts(
        Revenues=[_row("2022-12-31", 100.0), _row("2025-12-31", 200.0)],
        GrossProfit=[_row("2025-12-31", 80.0)],
    )

    assert "gross_margin_change_3y" not in _trends(facts)


def test_long_term_debt_growth_from_a_loss_free_base() -> None:
    facts = _facts(
        Revenues=[_row("2025-12-31", 1.0)],
        LongTermDebtNoncurrent=[_row("2022-12-31", 100.0, days=None),
                                _row("2025-12-31", 150.0, days=None)],
    )

    assert _trends(facts)["long_term_debt_change_3y_pct"].value == pytest.approx(0.5)


def test_loss_years_counts_losses_in_the_last_three_years() -> None:
    facts = _facts(NetIncomeLoss=[
        _row("2022-12-31", -50.0), _row("2023-12-31", -10.0),
        _row("2024-12-31", 20.0), _row("2025-12-31", -5.0),
    ])

    trends = _trends(facts)

    assert trends["net_loss_years_3y"].value == 2.0  # 2023 and 2025
    assert trends["net_loss_years_3y"].unit == "count"


def test_loss_years_needs_three_consecutive_years() -> None:
    facts = _facts(NetIncomeLoss=[
        _row("2021-12-31", -50.0), _row("2024-12-31", -10.0), _row("2025-12-31", -5.0),
    ])

    assert "net_loss_years_3y" not in _trends(facts)


def _shares(*pairs: tuple[str, float]) -> dict:
    return {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        _row(end, val, days=None, filed=end) for end, val in pairs]}}}}


def test_share_dilution_over_three_years() -> None:
    facts = _shares(("2023-02-10", 100.0), ("2024-02-10", 110.0),
                    ("2025-02-10", 120.0), ("2026-02-10", 130.0))

    assert _trends(facts)["share_count_change_3y_pct"].value == pytest.approx(0.30)


def test_share_buybacks_give_negative_change() -> None:
    facts = _shares(("2023-02-10", 100.0), ("2024-02-10", 95.0),
                    ("2025-02-10", 90.0), ("2026-02-10", 85.0))

    assert _trends(facts)["share_count_change_3y_pct"].value == pytest.approx(-0.15)


def test_stock_split_is_not_reported_as_dilution() -> None:
    """A 3-for-1 split triples the as-filed count; calling that 200% dilution
    would be wrong, so the metric is skipped."""
    facts = _shares(("2023-02-10", 100.0), ("2024-02-10", 300.0),
                    ("2025-02-10", 298.0), ("2026-02-10", 295.0))

    assert "share_count_change_3y_pct" not in _trends(facts)


def test_stale_share_count_is_not_used() -> None:
    facts = _shares(("2019-02-10", 100.0), ("2020-02-10", 110.0),
                    ("2021-02-10", 120.0), ("2022-02-10", 130.0))

    assert "share_count_change_3y_pct" not in _trends(facts)


# ----------------------------------------------------------------- integration


def test_extract_all_includes_trends_without_extra_requests() -> None:
    calls: list[str] = []

    class Client:
        def get_json(self, url: str) -> dict:
            calls.append(url)
            return {"facts": _revenue(("2024-12-31", 100.0), ("2025-12-31", 110.0))}

    snapshots = extract_all(Client(), _filing())

    assert len(calls) == 1
    assert {s.metric_key for s in snapshots} >= {"revenue", "revenue_yoy_pct"}


# ---------------------------------------------------------------- real filers


def _real(ticker: str) -> dict:
    data = json.loads((FIXTURES / f"{ticker}_facts.json").read_text())
    filing = FilingRecord(**data["filing"])
    current = extract_metrics_from_facts(data["facts"], filing)
    return {m.metric_key: m for m in derive_trends(data["facts"], filing, current)}


@pytest.mark.parametrize(
    "ticker,prior,current",
    [
        # Revenue in millions, read from each filing's income statement.
        ("jpm", 177_556, 182_447),
        ("mrna", 3_236, 1_944),
        ("mcd", 25_920, 26_885),
        ("xom", 349_585, 332_238),
        ("wmt", 674_538, 706_413),
    ],
)
def test_revenue_yoy_matches_the_filing(ticker, prior, current) -> None:
    assert _real(ticker)["revenue_yoy_pct"].value == pytest.approx(
        (current - prior) / prior
    )


def test_collapsing_vaccine_revenue_shows_in_the_three_year_trend() -> None:
    trends = _real("mrna")

    # FY2022 revenue of $19,263M (SEC data) to $1,944M in FY2025.
    assert trends["revenue_cagr_3y"].value == pytest.approx(
        (1_944 / 19_263) ** (1 / 3) - 1
    )
    assert trends["net_loss_years_3y"].value == 3.0


def test_profitable_filers_have_no_recent_loss_years() -> None:
    for ticker in ("jpm", "mcd", "wmt", "xom"):
        assert _real(ticker)["net_loss_years_3y"].value == 0.0, ticker


def test_walmart_split_does_not_register_as_share_dilution() -> None:
    """WMT's 3-for-1 split in 2024 triples the as-filed share count."""
    assert "share_count_change_3y_pct" not in _real("wmt")


def test_xom_trend_uses_the_tag_it_actually_reports() -> None:
    trends = _real("xom")

    assert trends["revenue_yoy_pct"].xbrl_tag == "Revenues (yoy)"
    assert trends["long_term_debt_change_3y_pct"].value < 0  # debt was paid down


def test_bank_has_no_debt_trend_without_a_current_debt_figure() -> None:
    assert "long_term_debt_change_3y_pct" not in _real("jpm")


# -------------------------------------------------------------------- history


def test_history_returns_recent_years_oldest_first_capped_at_five() -> None:
    from app.xbrl.trends import metric_history

    years = range(2018, 2026)
    facts = _revenue(*[(f"{y}-12-31", 100.0 + y) for y in years])

    points = metric_history(facts, _filing())["revenue"]["points"]

    assert [end.year for end, _ in points] == [2021, 2022, 2023, 2024, 2025]
    assert metric_history(facts, _filing())["revenue"]["unit"] == "USD"


def test_history_omits_metrics_with_a_single_point() -> None:
    from app.xbrl.trends import metric_history

    assert metric_history(_revenue(("2025-12-31", 100.0)), _filing()) == {}


def test_history_includes_gross_margin_per_year() -> None:
    from app.xbrl.trends import metric_history

    facts = _facts(
        Revenues=[_row("2024-12-31", 100.0), _row("2025-12-31", 200.0)],
        GrossProfit=[_row("2024-12-31", 50.0), _row("2025-12-31", 80.0)],
    )

    margin = metric_history(facts, _filing())["gross_margin"]

    assert margin["unit"] == "ratio"
    assert [round(v, 2) for _, v in margin["points"]] == [0.5, 0.4]


def test_history_does_not_extend_past_the_analyzed_year() -> None:
    from app.xbrl.trends import metric_history

    filing = _filing(fye="2024-12-31", filed="2025-02-15")
    facts = _revenue(("2023-12-31", 1.0), ("2024-12-31", 2.0), ("2025-12-31", 3.0))

    points = metric_history(facts, filing)["revenue"]["points"]

    assert points[-1][0] == date(2024, 12, 31)


def test_real_filer_history_matches_the_filing() -> None:
    from app.xbrl.trends import metric_history

    data = json.loads((FIXTURES / "mrna_facts.json").read_text())
    history = metric_history(data["facts"], FilingRecord(**data["filing"]))

    revenue = {end.year: v for end, v in history["revenue"]["points"]}
    assert revenue[2025] == 1_944_000_000 and revenue[2024] == 3_236_000_000
    losses = [v for _, v in history["net_income"]["points"] if v < 0]
    assert len(losses) == 3
