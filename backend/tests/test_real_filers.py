"""Offline regression tests against trimmed SEC Company Facts for real 10-Ks
(latest fiscal year as of Nov 2026). Fixtures in tests/fixtures/real_filers
keep only the tags in METRIC_TAGS for the filing's own accession.

Expected figures were read off each filing's financial statements (reported
in millions, so multiplied by 1e6 here) - not copied from extractor output.
"""

import json
from pathlib import Path

import pytest

from app.edgar.models import FilingRecord
from app.edgar.sector import classify_sector
from app.xbrl.derive import derive_ratios
from app.xbrl.extract import (
    extract_metrics_from_facts,
    extract_net_income_yoy_from_facts,
)

FIXTURES = Path(__file__).parent / "fixtures" / "real_filers"
M = 1_000_000


def _load(ticker: str) -> dict[str, object]:
    data = json.loads((FIXTURES / f"{ticker}_facts.json").read_text())
    filing = FilingRecord(**data["filing"])
    snaps = extract_metrics_from_facts(data["facts"], filing)
    snaps += derive_ratios(snaps, sector=classify_sector(filing.sic))
    yoy = extract_net_income_yoy_from_facts(data["facts"], filing, snaps)
    if yoy:
        snaps.append(yoy)
    return {s.metric_key: s for s in snaps}


@pytest.mark.parametrize(
    "ticker,expected",
    [
        ("jpm", {"revenue": 182_447, "net_income": 57_048, "total_assets": 4_424_900,
                 "stockholders_equity": 362_438}),
        ("mrna", {"revenue": 1_944, "net_income": -2_822, "total_assets": 12_338,
                  "stockholders_equity": 8_650}),
        ("mcd", {"revenue": 26_885, "net_income": 8_563, "total_assets": 59_515,
                 "stockholders_equity": -1_791}),
        ("wmt", {"revenue": 706_413, "net_income": 21_893, "total_assets": 284_668,
                 "stockholders_equity": 99_617}),
        ("xom", {"revenue": 332_238, "net_income": 28_844, "total_assets": 448_980,
                 "stockholders_equity": 259_386}),
    ],
)
def test_headline_figures_match_the_filing(ticker, expected) -> None:
    metrics = _load(ticker)

    for key, millions in expected.items():
        assert metrics[key].value == millions * M, key


def test_bank_lacks_classified_balance_sheet_metrics() -> None:
    """A bank holding company reports no current/non-current split, so those
    metrics are skipped rather than guessed."""
    metrics = _load("jpm")

    assert not set(metrics) & {"current_assets", "current_liabilities",
                               "working_capital_ratio", "operating_income"}
    assert metrics["short_term_debt"].xbrl_tag == "ShortTermBorrowings"
    assert metrics["liabilities_to_assets"].value == pytest.approx(0.918, abs=0.001)


def test_bank_cash_runway_is_not_derived_despite_negative_operating_cash_flow() -> None:
    """JPM's operating cash flow is negative because of trading and loan
    growth, not cash burn, so a runway figure would be misleading."""
    metrics = _load("jpm")

    assert metrics["operating_cash_flow"].value < 0
    assert "cash_runway_months" not in metrics


def test_loss_making_biotech_runway_and_improving_yoy() -> None:
    metrics = _load("mrna")

    assert metrics["cash_runway_months"].value == pytest.approx(16.6, abs=0.1)
    assert metrics["operating_income"].value < 0
    # The loss narrowed year over year, so YoY reads as an improvement.
    assert metrics["net_income_yoy_pct"].value == pytest.approx(0.2075, abs=0.001)
    assert metrics["debt_to_equity"].value == pytest.approx(0.068, abs=0.001)


def test_negative_equity_filer_skips_debt_to_equity_but_derives_liabilities() -> None:
    metrics = _load("mcd")

    assert "debt_to_equity" not in metrics
    assert metrics["total_liabilities"].source == "derived"
    assert metrics["liabilities_to_assets"].value > 1.0
    assert metrics["interest_coverage"].value == pytest.approx(7.83, abs=0.01)
    # No balance-sheet share count tag: falls back to the cover page.
    assert metrics["shares_outstanding"].xbrl_tag == "EntityCommonStockSharesOutstanding"


def test_retailer_with_january_year_end_resolves_to_its_own_year() -> None:
    metrics = _load("wmt")

    assert metrics["interest_expense"].xbrl_tag == "InterestExpenseDebt"
    assert metrics["working_capital_ratio"].value < 1.0
    assert metrics["net_income_yoy_pct"].value == pytest.approx(0.1264, abs=0.001)
    assert metrics["debt_to_equity"].value == pytest.approx(0.383, abs=0.001)


def test_energy_filer_uses_lease_inclusive_long_term_debt_tag() -> None:
    metrics = _load("xom")

    assert metrics["long_term_debt"].xbrl_tag == "LongTermDebtAndCapitalLeaseObligations"
    assert "cash_runway_months" not in metrics
    assert metrics["net_income_yoy_pct"].value < 0
