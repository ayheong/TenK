from pathlib import Path

from app.edgar.client import Client
from app.edgar.models import FilingRecord, FilingSummary

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_ROOT = Path("data/cache")


def submissions_url(cik: int) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik:010d}.json"


def filing_document_url(cik: int, accession: str, primary_document: str) -> str:
    accession_nodash = accession.replace("-", "")
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession_nodash}/{primary_document}"
    )


def cache_path(cik: int, accession: str, primary_document: str) -> Path:
    return CACHE_ROOT / str(cik) / accession / primary_document


def lookup_cik(client: Client, ticker: str) -> int:
    """Return SEC CIK for a stock ticker."""
    target = ticker.upper()
    data = client.get_json(COMPANY_TICKERS_URL)

    for entry in data.values():
        if entry["ticker"].upper() == target:
            return int(entry["cik_str"])

    raise ValueError(f"Ticker not found: {ticker}")


def find_10k_filings(client: Client, cik: int) -> list[FilingSummary]:
    """Return 10-K filings for a CIK, most recent first."""
    data = client.get_json(submissions_url(cik))
    recent = data["filings"]["recent"]
    fiscal_year_ends = recent.get("reportDate", [None] * len(recent["form"]))

    return [
        FilingSummary(
            accession=accession,
            filing_date=filing_date,
            primary_document=primary_document,
            fiscal_year_end=fiscal_year_end,
        )
        for form, accession, filing_date, primary_document, fiscal_year_end in zip(
            recent["form"],
            recent["accessionNumber"],
            recent["filingDate"],
            recent["primaryDocument"],
            fiscal_year_ends,
            strict=True,
        )
        if form == "10-K"
    ]


def find_latest_10k(client: Client, cik: int) -> FilingSummary:
    """Return the most recent 10-K filing."""
    filings = find_10k_filings(client, cik)
    if not filings:
        raise ValueError(f"No 10-K found for CIK {cik}")
    return filings[0]


def fetch_filing_html(
    client: Client, cik: int, accession: str, primary_document: str
) -> Path:
    """Download a filing's primary HTML document, caching it on disk.

    Skips the request entirely if the accession was already downloaded.
    """
    path = cache_path(cik, accession, primary_document)
    if not path.exists():
        html = client.get_text(filing_document_url(cik, accession, primary_document))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    return path


def resolve_filing(ticker: str) -> FilingRecord:
    """Ticker → latest 10-K metadata + cached HTML under data/cache/."""
    client = Client()
    cik = lookup_cik(client, ticker)
    filings = find_10k_filings(client, cik)
    if not filings:
        raise ValueError(f"No 10-K found for CIK {cik}")

    latest = filings[0]
    prior_accession = filings[1].accession if len(filings) > 1 else None
    cached = fetch_filing_html(client, cik, latest.accession, latest.primary_document)

    return FilingRecord(
        ticker=ticker.upper(),
        cik=cik,
        accession=latest.accession,
        filing_date=latest.filing_date,
        fiscal_year_end=latest.fiscal_year_end,
        html_url=filing_document_url(cik, latest.accession, latest.primary_document),
        cached_path=str(cached),
        prior_accession=prior_accession,
    )
