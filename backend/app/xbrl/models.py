from datetime import date
from typing import Literal

from pydantic import BaseModel


class MetricSnapshot(BaseModel):
    ticker: str
    cik: int
    fiscal_year: int
    metric_key: str
    value: float
    unit: str
    xbrl_tag: str
    source: Literal["company_facts", "inline_xbrl", "derived"]
    filed_at: date
