from datetime import date

from pydantic import BaseModel


class FilingSummary(BaseModel):
    accession: str
    filing_date: str
    primary_document: str
    fiscal_year_end: str | None = None


class FilingRecord(BaseModel):
    ticker: str
    cik: int
    accession: str
    form_type: str = "10-K"
    filing_date: date
    fiscal_year_end: date | None = None
    html_url: str
    cached_path: str
    prior_accession: str | None = None
