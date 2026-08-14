from app.edgar.client import Client
from app.edgar.models import FilingRecord

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def submissions_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik:010d}.json"


def lookup_cik(client: Client, ticker: str) -> int:
    """Return SEC CIK for a stock ticker."""
    target = ticker.upper()
    data = client.get_json(COMPANY_TICKERS_URL)

    for entry in data.values():
        if entry["ticker"].upper() == target:
            return int(entry["cik_str"])

    raise ValueError(f"Ticker not found: {ticker}")


def find_latest_10k(client: Client, cik: int) -> tuple[str, str]:
    """Return (accession, filing_date) for the most recent 10-K."""
    data = client.get_json(submissions_url(cik))
    recent = data["filings"]["recent"]

    for form, accession, filing_date in zip(
        recent["form"],
        recent["accessionNumber"],
        recent["filingDate"],
        strict=True,
    ):
        if form == "10-K":
            return accession, filing_date

    raise ValueError(f"No 10-K found for CIK {cik}")


def resolve_filing(ticker: str) -> FilingRecord:
    """Ticker → latest 10-K metadata + cached HTML under data/cache/."""
    raise NotImplementedError
