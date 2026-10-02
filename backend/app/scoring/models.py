# Risk scoring output schema. See ROADMAP.md "Output schema" for the full
# spec and rationale - subscores/signals are kept open-ended (not a fixed
# five) so a future market_price family can register without touching
# this file or the aggregation logic.

from typing import Literal

from pydantic import BaseModel

Band = Literal["low", "elevated", "high", "severe"]
Confidence = Literal["high", "medium", "low"]
SubscoreKey = Literal[
    "liquidity", "leverage", "litigation_regulatory", "governance", "disclosure_change"
]
SubscoreFamily = Literal["financial_fundamentals", "legal_governance", "disclosure"]
SignalKind = Literal["quantitative", "qualitative"]
SignalDirection = Literal["raises", "lowers"]
UnavailableCode = Literal["missing_input"]


class Signal(BaseModel):
    key: str
    kind: SignalKind
    raw_value: float | str
    direction: SignalDirection
    contribution: float
    source: str


class Subscore(BaseModel):
    key: SubscoreKey
    family: SubscoreFamily
    score: float
    weight: float
    yoy_delta: float | None = None
    available: bool
    reason_code: UnavailableCode | None = None
    reason: str | None = None
    signals: list[Signal] = []


class RiskScore(BaseModel):
    overall: float
    band: Band
    confidence: Confidence
    accession: str
    fiscal_year: int
    sector: str | None = None
    sector_percentile: float | None = None
    subscores: list[Subscore]
    overrides_applied: list[str] = []
    data_gaps: list[str] = []
