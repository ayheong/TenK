import httpx
import pytest
import respx

from app.edgar.client import Client
from app.edgar.resolve import (
    COMPANY_TICKERS_URL,
    find_latest_10k,
    lookup_cik,
    submissions_url,
)

TICKERS_FIXTURE = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}

SUBMISSIONS_FIXTURE = {
    "filings": {
        "recent": {
            "form": ["10-Q", "10-K", "8-K"],
            "accessionNumber": [
                "0000320193-25-000001",
                "0000320193-25-000079",
                "0000320193-25-000002",
            ],
            "filingDate": ["2025-01-31", "2025-10-31", "2025-11-15"],
        }
    }
}


@respx.mock
def test_lookup_cik_returns_cik_for_ticker() -> None:
    respx.get(COMPANY_TICKERS_URL).mock(
        return_value=httpx.Response(200, json=TICKERS_FIXTURE)
    )
    client = Client()

    assert lookup_cik(client, "AAPL") == 320193
    assert lookup_cik(client, "aapl") == 320193


@respx.mock
def test_lookup_cik_raises_for_unknown_ticker() -> None:
    respx.get(COMPANY_TICKERS_URL).mock(
        return_value=httpx.Response(200, json=TICKERS_FIXTURE)
    )
    client = Client()

    with pytest.raises(ValueError, match="Ticker not found"):
        lookup_cik(client, "NOTREAL")


@respx.mock
def test_find_latest_10k_returns_first_10k() -> None:
    respx.get(submissions_url(320193)).mock(
        return_value=httpx.Response(200, json=SUBMISSIONS_FIXTURE)
    )
    client = Client()

    accession, filing_date = find_latest_10k(client, 320193)

    assert accession == "0000320193-25-000079"
    assert filing_date == "2025-10-31"


@respx.mock
def test_find_latest_10k_raises_when_missing() -> None:
    respx.get(submissions_url(320193)).mock(
        return_value=httpx.Response(
            200,
            json={
                "filings": {
                    "recent": {
                        "form": ["10-Q", "8-K"],
                        "accessionNumber": ["0000320193-25-000001", "0000320193-25-000002"],
                        "filingDate": ["2025-01-31", "2025-11-15"],
                    }
                }
            },
        )
    )
    client = Client()

    with pytest.raises(ValueError, match="No 10-K found"):
        find_latest_10k(client, 320193)
