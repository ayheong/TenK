import httpx
import pytest
import respx

from app.edgar import resolve
from app.edgar.client import Client
from app.edgar.resolve import (
    COMPANY_TICKERS_URL,
    fetch_filing_html,
    filing_document_url,
    find_10k_filings,
    find_latest_10k,
    lookup_cik,
    resolve_filing,
    submissions_url,
)

CIK = 320193

TICKERS_FIXTURE = {
    "0": {"cik_str": CIK, "ticker": "AAPL", "title": "Apple Inc."},
}

SUBMISSIONS_FIXTURE = {
    "filings": {
        "recent": {
            "form": ["10-Q", "10-K", "8-K", "10-K"],
            "accessionNumber": [
                "0000320193-25-000001",
                "0000320193-25-000079",
                "0000320193-25-000002",
                "0000320193-24-000081",
            ],
            "filingDate": [
                "2025-01-31",
                "2025-10-31",
                "2025-11-15",
                "2024-11-01",
            ],
            "primaryDocument": [
                "aapl-20241228.htm",
                "aapl-20250927.htm",
                "aapl-8k.htm",
                "aapl-20240928.htm",
            ],
            "reportDate": [
                "2024-12-28",
                "2025-09-27",
                "",
                "2024-09-28",
            ],
        }
    }
}


@respx.mock
def test_lookup_cik_returns_cik_for_ticker() -> None:
    respx.get(COMPANY_TICKERS_URL).mock(
        return_value=httpx.Response(200, json=TICKERS_FIXTURE)
    )
    client = Client()

    assert lookup_cik(client, "AAPL") == CIK
    assert lookup_cik(client, "aapl") == CIK


@respx.mock
def test_lookup_cik_raises_for_unknown_ticker() -> None:
    respx.get(COMPANY_TICKERS_URL).mock(
        return_value=httpx.Response(200, json=TICKERS_FIXTURE)
    )
    client = Client()

    with pytest.raises(ValueError, match="Ticker not found"):
        lookup_cik(client, "NOTREAL")


@respx.mock
def test_find_10k_filings_returns_most_recent_first() -> None:
    respx.get(submissions_url(CIK)).mock(
        return_value=httpx.Response(200, json=SUBMISSIONS_FIXTURE)
    )
    client = Client()

    filings = find_10k_filings(client, CIK)

    assert [f.accession for f in filings] == [
        "0000320193-25-000079",
        "0000320193-24-000081",
    ]
    assert filings[0].primary_document == "aapl-20250927.htm"
    assert filings[0].fiscal_year_end == "2025-09-27"


@respx.mock
def test_find_latest_10k_returns_first_10k() -> None:
    respx.get(submissions_url(CIK)).mock(
        return_value=httpx.Response(200, json=SUBMISSIONS_FIXTURE)
    )
    client = Client()

    latest = find_latest_10k(client, CIK)

    assert latest.accession == "0000320193-25-000079"
    assert latest.filing_date == "2025-10-31"


@respx.mock
def test_find_latest_10k_raises_when_missing() -> None:
    respx.get(submissions_url(CIK)).mock(
        return_value=httpx.Response(
            200,
            json={
                "filings": {
                    "recent": {
                        "form": ["10-Q", "8-K"],
                        "accessionNumber": [
                            "0000320193-25-000001",
                            "0000320193-25-000002",
                        ],
                        "filingDate": ["2025-01-31", "2025-11-15"],
                        "primaryDocument": ["a.htm", "b.htm"],
                        "reportDate": ["2025-01-31", ""],
                    }
                }
            },
        )
    )
    client = Client()

    with pytest.raises(ValueError, match="No 10-K found"):
        find_latest_10k(client, CIK)


def test_filing_document_url_strips_dashes_from_accession() -> None:
    url = filing_document_url(CIK, "0000320193-25-000079", "aapl-20250927.htm")

    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019325000079/aapl-20250927.htm"
    )


@respx.mock
def test_fetch_filing_html_downloads_and_caches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(resolve, "CACHE_ROOT", tmp_path)
    route = respx.get(
        filing_document_url(CIK, "0000320193-25-000079", "aapl-20250927.htm")
    ).mock(return_value=httpx.Response(200, text="<html>10-K</html>"))
    client = Client()

    path = fetch_filing_html(client, CIK, "0000320193-25-000079", "aapl-20250927.htm")

    assert path.read_text() == "<html>10-K</html>"
    assert route.call_count == 1

    # Second call should hit the cache, not the network.
    path_again = fetch_filing_html(
        client, CIK, "0000320193-25-000079", "aapl-20250927.htm"
    )

    assert path_again == path
    assert route.call_count == 1


@respx.mock
def test_resolve_filing_returns_populated_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(resolve, "CACHE_ROOT", tmp_path)
    respx.get(COMPANY_TICKERS_URL).mock(
        return_value=httpx.Response(200, json=TICKERS_FIXTURE)
    )
    respx.get(submissions_url(CIK)).mock(
        return_value=httpx.Response(200, json=SUBMISSIONS_FIXTURE)
    )
    respx.get(
        filing_document_url(CIK, "0000320193-25-000079", "aapl-20250927.htm")
    ).mock(return_value=httpx.Response(200, text="<html>10-K</html>"))

    record = resolve_filing("AAPL")

    assert record.ticker == "AAPL"
    assert record.cik == CIK
    assert record.accession == "0000320193-25-000079"
    assert str(record.filing_date) == "2025-10-31"
    assert str(record.fiscal_year_end) == "2025-09-27"
    assert record.prior_accession == "0000320193-24-000081"
    assert record.cached_path.endswith("aapl-20250927.htm")
