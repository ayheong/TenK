import httpx
import respx

from app.edgar.client import Client
from app.edgar.models import FilingRecord
from app.xbrl.derive import derive_ratios
from app.xbrl.extract import (
    company_facts_url,
    extract_all,
    extract_metrics,
    extract_metrics_from_facts,
    extract_net_income_yoy_from_facts,
)

CIK = 320193
ACCESSION = "0000320193-25-000079"
FISCAL_YEAR_END = "2025-09-27"

FILING = FilingRecord(
    ticker="AAPL",
    cik=CIK,
    accession=ACCESSION,
    filing_date="2025-10-31",
    fiscal_year_end=FISCAL_YEAR_END,
    html_url="https://example.com/aapl-20250927.htm",
    cached_path="data/cache/320193/0000320193-25-000079/aapl-20250927.htm",
)

FACTS_FIXTURE = {
    "facts": {
        "us-gaap": {
            # Primary revenue tag absent -> should fall back to "Revenues".
            "Revenues": {
                "units": {
                    "USD": [
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 391035000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        },
                        {
                            "start": "2024-09-29",
                            "end": FISCAL_YEAR_END,
                            "val": 416161000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        },
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "start": "2023-10-01",
                            "end": "2024-09-28",
                            "val": 93736000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        },
                        {
                            "start": "2024-09-29",
                            "end": FISCAL_YEAR_END,
                            "val": 112010000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        },
                    ]
                }
            },
            "LongTermDebtNoncurrent": {
                "units": {
                    "USD": [
                        {
                            "end": FISCAL_YEAR_END,
                            "val": 78328000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            },
            "GrossProfit": {
                "units": {
                    "USD": [
                        {
                            "start": "2024-09-29",
                            "end": FISCAL_YEAR_END,
                            "val": 195201000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            },
            "ResearchAndDevelopmentExpense": {
                "units": {
                    "USD": [
                        {
                            "start": "2024-09-29",
                            "end": FISCAL_YEAR_END,
                            "val": 34550000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            },
            "AssetsCurrent": {
                "units": {
                    "USD": [
                        {
                            "end": FISCAL_YEAR_END,
                            "val": 147957000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            },
            "LiabilitiesCurrent": {
                "units": {
                    "USD": [
                        {
                            "end": FISCAL_YEAR_END,
                            "val": 165631000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            },
        },
        "dei": {
            # us-gaap:CommonStockSharesOutstanding is missing; this cover-page
            # tag reports as of a date after the fiscal year end, so matching
            # must fall back to accession-only.
            "EntityCommonStockSharesOutstanding": {
                "units": {
                    "shares": [
                        {
                            "end": "2025-10-17",
                            "val": 14776353000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            }
        },
    }
}


@respx.mock
def test_extract_metrics_maps_canonical_keys() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_metrics(client, FILING)
    by_key = {s.metric_key: s for s in snapshots}

    assert by_key["net_income"].value == 112010000000
    assert by_key["net_income"].xbrl_tag == "NetIncomeLoss"
    assert by_key["net_income"].source == "company_facts"
    assert by_key["net_income"].unit == "USD"
    assert by_key["net_income"].fiscal_year == 2025


@respx.mock
def test_extract_metrics_falls_back_to_secondary_tag() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_metrics(client, FILING)
    revenue = next(s for s in snapshots if s.metric_key == "revenue")

    assert revenue.xbrl_tag == "Revenues"
    assert revenue.value == 416161000000


@respx.mock
def test_extract_metrics_picks_correct_fiscal_year_row() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_metrics(client, FILING)
    revenue = next(s for s in snapshots if s.metric_key == "revenue")

    # The fixture also has a 2024 row for the same accession/tag; the
    # fiscal-year-end-matched 2025 row must win, not the first in the list.
    assert revenue.value != 391035000000
    assert revenue.value == 416161000000


@respx.mock
def test_extract_metrics_falls_back_across_taxonomy_by_accession() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_metrics(client, FILING)
    shares = next(s for s in snapshots if s.metric_key == "shares_outstanding")

    assert shares.xbrl_tag == "EntityCommonStockSharesOutstanding"
    assert shares.value == 14776353000
    assert shares.unit == "shares"


@respx.mock
def test_extract_metrics_skips_missing_metrics() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_metrics(client, FILING)
    keys = {s.metric_key for s in snapshots}

    # Not present anywhere in the fixture for any candidate tag.
    assert "operating_cash_flow" not in keys
    assert "short_term_debt" not in keys


def test_derive_ratios_computes_gross_margin_and_rd_pct_revenue() -> None:
    snapshots = extract_metrics_from_facts(FACTS_FIXTURE["facts"], FILING)

    derived = {s.metric_key: s for s in derive_ratios(snapshots)}

    assert derived["gross_margin"].value == 195201000000 / 416161000000
    assert derived["gross_margin"].unit == "ratio"
    assert derived["gross_margin"].source == "derived"
    assert derived["gross_margin"].xbrl_tag == "gross_profit/revenue"
    assert derived["rd_pct_revenue"].value == 34550000000 / 416161000000
    assert derived["working_capital_ratio"].value == 147957000000 / 165631000000
    assert derived["working_capital_ratio"].xbrl_tag == (
        "current_assets/current_liabilities"
    )


def test_derive_ratios_skips_when_an_input_is_missing() -> None:
    snapshots = [s for s in extract_metrics_from_facts(FACTS_FIXTURE["facts"], FILING)
                 if s.metric_key != "gross_profit"]

    derived = {s.metric_key: s for s in derive_ratios(snapshots)}

    assert "gross_margin" not in derived
    assert "rd_pct_revenue" in derived


def test_extract_net_income_yoy_from_facts_computes_change() -> None:
    current = extract_metrics_from_facts(FACTS_FIXTURE["facts"], FILING)

    yoy = extract_net_income_yoy_from_facts(FACTS_FIXTURE["facts"], FILING, current)

    assert yoy is not None
    assert yoy.metric_key == "net_income_yoy_pct"
    assert yoy.value == (112010000000 - 93736000000) / 93736000000
    assert yoy.unit == "ratio"
    assert yoy.source == "derived"


def test_extract_net_income_yoy_from_facts_returns_none_without_prior_year() -> None:
    facts = {
        "us-gaap": {
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "start": "2024-09-29",
                            "end": FISCAL_YEAR_END,
                            "val": 112010000000,
                            "accn": ACCESSION,
                            "fy": 2025,
                            "form": "10-K",
                            "filed": "2025-10-31",
                        }
                    ]
                }
            }
        }
    }
    current = extract_metrics_from_facts(facts, FILING)

    assert extract_net_income_yoy_from_facts(facts, FILING, current) is None


@respx.mock
def test_extract_all_includes_current_derived_and_yoy_metrics() -> None:
    respx.get(company_facts_url(CIK)).mock(
        return_value=httpx.Response(200, json=FACTS_FIXTURE)
    )
    client = Client()

    snapshots = extract_all(client, FILING)
    keys = {s.metric_key for s in snapshots}

    assert {
        "net_income",
        "revenue",
        "gross_margin",
        "rd_pct_revenue",
        "working_capital_ratio",
    } <= keys
    assert "net_income_yoy_pct" in keys
