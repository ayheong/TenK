# Pydantic schemas for qualitative extraction.
#
# Each *target* model (RiskFactorChanges, ManagementTone, ...) is what an
# LLM call is constrained to produce for one filing section. Field names
# and Literal sets are deliberately close to what risk scoring
# will consume - booleans and enums it can turn into subscore signals
# without re-reading prose. `SectionExtraction` wraps one target result
# with provenance; `QualitativeExtraction` bundles all of them for a
# filing (mirrors CONTEXT.md's SectionExtraction data-model entry).

from typing import Literal

from pydantic import BaseModel, Field

RiskCategory = Literal[
    "financial",
    "operational",
    "legal",
    "regulatory",
    "macroeconomic",
    "cybersecurity",
    "supply_chain",
    "competition",
    "governance",
    "other",
]

# How urgent the disclosure *language* is, independent of the underlying
# fact - "could adversely affect" (routine) vs "raises substantial doubt"
# (severe). The Disclosure-Change subscore keys off escalation
# here, not off the raw count of risk factors.
SeverityLanguage = Literal["routine", "elevated", "severe"]


class RiskFactorItem(BaseModel):
    title: str = Field(description="Short label for the risk factor")
    category: RiskCategory
    severity_language: SeverityLanguage = Field(
        description=(
            "Tone of the disclosure: routine boilerplate, elevated concern, "
            "or severe/urgent framing"
        )
    )
    summary: str = Field(description="One-sentence plain-language summary")


class RiskFactorChanges(BaseModel):
    added: list[RiskFactorItem] = Field(
        default_factory=list,
        description="Risk factors present this year but not the prior year",
    )
    removed: list[str] = Field(
        default_factory=list,
        description="Titles of risk factors dropped since the prior year",
    )
    escalated: list[RiskFactorItem] = Field(
        default_factory=list,
        description="Risk factors whose language materially intensified year-over-year",
    )
    net_change: Literal["expanded", "reduced", "unchanged"] = Field(
        description="Overall direction of risk-factor disclosure vs the prior year"
    )
    prior_year_available: bool = Field(
        description="False if no prior-year Item 1A was provided for comparison"
    )
    summary: str


class ManagementTone(BaseModel):
    overall_tone: Literal["optimistic", "balanced", "cautious", "negative"]
    hedging_intensity: Literal["low", "moderate", "high"] = Field(
        description="How heavily the discussion is qualified with uncertainty language"
    )
    forward_guidance: list[str] = Field(
        default_factory=list,
        description="Specific forward-looking statements about future performance",
    )
    notable_concerns: list[str] = Field(
        default_factory=list,
        description="Concerns management raises about the business outlook",
    )
    summary: str


class GoingConcernOpinion(BaseModel):
    auditor_opinion_type: Literal[
        "unqualified", "qualified", "adverse", "disclaimer", "not_found"
    ] = Field(description="Type of opinion the independent auditor expressed")
    going_concern_doubt: bool = Field(
        description=(
            "True if the filing or its auditor expresses substantial doubt about "
            "the company's ability to continue as a going concern"
        )
    )
    material_weakness: bool = Field(
        description=(
            "True if a material weakness in internal control over financial "
            "reporting is disclosed"
        )
    )
    evidence: str = Field(
        description="Short quote or close paraphrase from the text supporting the above"
    )
    summary: str


class RelatedPartyItem(BaseModel):
    counterparty: str
    nature: str = Field(description="What the transaction is")
    amount_text: str | None = Field(
        default=None, description="Dollar amount as stated in the text, if any"
    )
    concern_level: Literal["routine", "noteworthy", "concerning"]


class RelatedPartyTransactions(BaseModel):
    has_related_party_transactions: bool
    transactions: list[RelatedPartyItem] = Field(default_factory=list)
    summary: str


class RevenueConcentration(BaseModel):
    customer_concentration: bool = Field(
        description=(
            "True if a small number of customers account for a large share of revenue"
        )
    )
    largest_customer_pct_text: str | None = Field(
        default=None,
        description="Stated share for the largest customer (e.g. '18% of net revenue')",
    )
    named_customers: list[str] = Field(
        default_factory=list, description="Customers named in the text, if any"
    )
    geographic_concentration: str | None = Field(
        default=None,
        description="Notable geographic revenue concentration, if disclosed",
    )
    summary: str


ExtractionType = Literal[
    "risk_factor_changes",
    "management_tone",
    "going_concern",
    "related_party",
    "revenue_concentration",
]

ParsedExtraction = (
    RiskFactorChanges
    | ManagementTone
    | GoingConcernOpinion
    | RelatedPartyTransactions
    | RevenueConcentration
)


class SectionExtraction(BaseModel):
    """One target result plus provenance. `found=False` means the source
    section couldn't be located in the filing (no LLM call was made);
    `error` is set when the section was found but the LLM call failed or
    refused. `parsed` is populated only on success."""

    extraction_type: ExtractionType
    item_number: str
    found: bool
    parsed: ParsedExtraction | None = None
    method: Literal["llm", "rules"] = Field(
        default="llm",
        description="Whether `parsed` came from the LLM or deterministic rules",
    )
    source_chars: int = Field(
        default=0, description="Characters of section text sent to the LLM"
    )
    error: str | None = None
    reason: str | None = Field(
        default=None,
        description="Parser not-found reason, or a note (e.g. text was truncated)",
    )


class QualitativeExtraction(BaseModel):
    ticker: str
    cik: int
    accession: str
    prior_accession: str | None = None
    model_version: str
    risk_factor_changes: SectionExtraction
    management_tone: SectionExtraction
    going_concern: SectionExtraction
    related_party: SectionExtraction
    revenue_concentration: SectionExtraction
