from app.edgar.client import Client
from app.edgar.models import FilingRecord

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def lookup_cik(client: Client, ticker: str) -> int:
    """Return SEC CIK for a stock ticker."""
    target = ticker.upper()
    data = client.get_json(COMPANY_TICKERS_URL)

    for entry in data.values():
        if entry["ticker"].upper() == target:
            return int(entry["cik_str"])

    raise ValueError(f"Ticker not found: {ticker}")


def resolve_filing(ticker: str) -> FilingRecord:
    """Ticker → latest 10-K metadata + cached HTML under data/cache/."""
    raise NotImplementedError
