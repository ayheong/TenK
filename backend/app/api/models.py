from datetime import date

from pydantic import BaseModel

from app.extraction.models import QualitativeExtraction
from app.scoring.models import Subscore


class FilingInfo(BaseModel):
    ticker: str
    cik: int
    accession: str
    prior_accession: str | None
    filing_date: date
    fiscal_year_end: date | None
    html_url: str


class MetricRow(BaseModel):
    key: str
    value: float
    unit: str
    xbrl_tag: str
    source: str


class Analysis(BaseModel):
    """Everything the pipeline produced for one ticker, for review in the demo.

    There is no overall score yet because aggregation is not built."""

    filing: FilingInfo
    llm_enabled: bool
    metrics: list[MetricRow]
    subscores: list[Subscore]
    extraction: QualitativeExtraction
