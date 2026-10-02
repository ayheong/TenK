from app.api.models import Analysis, FilingInfo, MetricRow
from app.edgar.client import Client
from app.edgar.resolve import resolve_filing_pair
from app.extraction.llm import ExtractionError, LLMClient
from app.extraction.pipeline import extract_qualitative
from app.scoring.disclosure import compute_disclosure_subscore
from app.scoring.governance import compute_governance_subscore
from app.scoring.leverage import compute_leverage_subscore
from app.scoring.liquidity import compute_liquidity_subscore
from app.scoring.litigation import compute_litigation_subscore
from app.xbrl.extract import extract_all

LLM_DISABLED_MESSAGE = "LLM disabled for this run"


class DisabledLLM:
    """Stands in for the LLM so the rule-based extractors run without any API
    spend. Sections that still need the model are recorded with an error."""

    model = "disabled"

    def extract(self, *, system: str, text: str, schema: type):
        raise ExtractionError(LLM_DISABLED_MESSAGE)


def analyze(ticker: str, *, use_llm: bool) -> Analysis:
    """Run the full pipeline for one ticker. Raises ValueError for an unknown
    ticker or one with no 10-K."""
    filing, prior = resolve_filing_pair(ticker)
    metrics = extract_all(Client(), filing)
    extraction = extract_qualitative(
        filing, prior, llm=LLMClient() if use_llm else DisabledLLM()
    )
    return Analysis(
        filing=FilingInfo(**filing.model_dump(include=set(FilingInfo.model_fields))),
        llm_enabled=use_llm,
        metrics=[
            MetricRow(
                key=m.metric_key,
                value=m.value,
                unit=m.unit,
                xbrl_tag=m.xbrl_tag,
                source=m.source,
            )
            for m in metrics
        ],
        subscores=[
            compute_liquidity_subscore(metrics),
            compute_leverage_subscore(metrics),
            compute_litigation_subscore(extraction),
            compute_governance_subscore(extraction),
            compute_disclosure_subscore(extraction),
        ],
        extraction=extraction,
    )
