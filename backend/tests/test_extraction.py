from types import SimpleNamespace

import pytest

from app.edgar.models import FilingRecord
from app.extraction import models
from app.extraction.llm import (
    ExtractionError,
    ExtractionRefused,
    LLMClient,
    extraction_model,
)
from app.extraction.pipeline import extract_qualitative

# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeLLM:
    """Stands in for LLMClient at the wrapper boundary. Returns a preset
    instance per schema and records every call; optionally raises."""

    def __init__(self, responses=None, error: Exception | None = None) -> None:
        self.model = "fake-model"
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[type, str, str]] = []

    def extract(self, *, system: str, text: str, schema):
        self.calls.append((schema, system, text))
        if self.error is not None:
            raise self.error
        if schema in self.responses:
            return self.responses[schema]
        raise AssertionError(f"no FakeLLM response registered for {schema.__name__}")


def _fake_anthropic(stop_reason="end_turn", parsed_output=None, explanation=None):
    response = SimpleNamespace(
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(explanation=explanation),
        parsed_output=parsed_output,
    )
    messages = SimpleNamespace(parse=lambda **kwargs: response)
    return SimpleNamespace(messages=messages)


DEFAULT_RESPONSES = {
    models.RiskFactorChanges: models.RiskFactorChanges(
        added=[],
        removed=[],
        escalated=[],
        net_change="unchanged",
        prior_year_available=True,
        summary="No material change.",
    ),
    models.ManagementTone: models.ManagementTone(
        overall_tone="balanced",
        hedging_intensity="moderate",
        forward_guidance=[],
        notable_concerns=[],
        summary="Measured discussion.",
    ),
    models.GoingConcernOpinion: models.GoingConcernOpinion(
        auditor_opinion_type="unqualified",
        going_concern_doubt=False,
        material_weakness=False,
        evidence="In our opinion, the financial statements present fairly...",
        summary="Clean opinion.",
    ),
    models.RelatedPartyTransactions: models.RelatedPartyTransactions(
        has_related_party_transactions=True,
        transactions=[
            models.RelatedPartyItem(
                counterparty="CEO",
                nature="Aircraft lease",
                amount_text="$1.2 million",
                concern_level="noteworthy",
            )
        ],
        summary="One related-party lease.",
    ),
    models.RevenueConcentration: models.RevenueConcentration(
        customer_concentration=True,
        largest_customer_pct_text="18% of net revenue",
        named_customers=["MegaCorp"],
        geographic_concentration=None,
        summary="One large customer.",
    ),
}


# --------------------------------------------------------------------------
# Filing HTML fixtures
# --------------------------------------------------------------------------

RISK_BODY = "Our business faces competition and could be adversely affected. " * 15
MDA_BODY = "Revenue grew and we expect continued demand next year. " * 15
BUSINESS_BODY = (
    "We sell products globally. One customer, MegaCorp, accounted for 18% of "
    "net revenue this year. " + "General business description follows. " * 15
)
AUDIT_BODY = (
    "Report of Independent Registered Public Accounting Firm. "
    "Opinion on the Financial Statements. In our opinion, the consolidated "
    "financial statements present fairly, in all material respects, the "
    "financial position of the Company. " * 8
)
RELATED_PARTY_BODY = (
    "Note 14. Related party transactions. The Company leases an aircraft from "
    "an entity controlled by its Chief Executive Officer for $1.2 million per "
    "year. " * 6
)
CONTROLS_BODY = (
    "Item 9A. Controls and Procedures. Management concluded that internal "
    "control over financial reporting was effective as of year end. " * 8
)


def _filing_html(*, related_party: bool = True, concentration: bool = True) -> str:
    business = BUSINESS_BODY if concentration else "General business description. " * 20
    financials = AUDIT_BODY + ("\n" + RELATED_PARTY_BODY if related_party else "")
    return f"""
<html><body>
<div><p>TABLE OF CONTENTS</p></div>
<table>
<tr><td>Item 1.</td><td>Business</td><td>1</td></tr>
<tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>
<tr><td>Item 7.</td><td>MD&amp;A</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements</td><td>28</td></tr>
<tr><td>Item 9A.</td><td>Controls and Procedures</td><td>52</td></tr>
</table>
<div><p>PART I</p></div>
<div><p>{"This Annual Report contains forward-looking statements. " * 15}</p></div>
<div><p>Item 1. Business</p><p>{business}</p></div>
<div><p>Item 1A. Risk Factors</p><p>{RISK_BODY}</p></div>
<div><p>Item 7. Management's Discussion and Analysis</p><p>{MDA_BODY}</p></div>
<div><p>Item 8. Financial Statements and Supplementary Data</p><p>{financials}</p></div>
<div><p>Item 9A. Controls and Procedures</p><p>{CONTROLS_BODY}</p></div>
</body></html>
"""


def _write_filing(tmp_path, name: str, html: str) -> FilingRecord:
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return FilingRecord(
        ticker="TEST",
        cik=111111,
        accession=f"0000000000-26-{name}",
        filing_date="2026-02-15",
        fiscal_year_end="2025-12-31",
        html_url=f"https://example.com/{name}",
        cached_path=str(path),
        prior_accession="0000000000-25-prior",
    )


# --------------------------------------------------------------------------
# LLMClient
# --------------------------------------------------------------------------


def test_llmclient_returns_parsed_output() -> None:
    parsed = DEFAULT_RESPONSES[models.ManagementTone]
    client = LLMClient(client=_fake_anthropic(parsed_output=parsed))

    result = client.extract(system="s", text="t", schema=models.ManagementTone)

    assert result is parsed


def test_llmclient_raises_on_refusal() -> None:
    client = LLMClient(
        client=_fake_anthropic(stop_reason="refusal", explanation="declined")
    )

    with pytest.raises(ExtractionRefused, match="declined"):
        client.extract(system="s", text="t", schema=models.ManagementTone)


def test_llmclient_raises_when_nothing_parsed() -> None:
    client = LLMClient(
        client=_fake_anthropic(stop_reason="max_tokens", parsed_output=None)
    )

    with pytest.raises(ExtractionError, match="no parseable ManagementTone"):
        client.extract(system="s", text="t", schema=models.ManagementTone)


def test_extraction_model_env_override(monkeypatch) -> None:
    monkeypatch.delenv("TENK_EXTRACTION_MODEL", raising=False)
    assert extraction_model() == "claude-opus-5"

    monkeypatch.setenv("TENK_EXTRACTION_MODEL", "claude-sonnet-5")
    assert extraction_model() == "claude-sonnet-5"
    assert LLMClient(client=object()).model == "claude-sonnet-5"


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


def test_pipeline_runs_every_extractor(tmp_path) -> None:
    filing = _write_filing(tmp_path, "current.htm", _filing_html())
    prior = _write_filing(tmp_path, "prior.htm", _filing_html())
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, prior, llm=llm)

    assert result.model_version == "fake-model"
    assert result.accession == filing.accession
    for section in (
        result.risk_factor_changes,
        result.management_tone,
        result.going_concern,
        result.related_party,
        result.revenue_concentration,
    ):
        assert section.found
        assert section.parsed is not None
        assert section.error is None

    # Risk-factor extractor got both years.
    rfc_call = next(c for c in llm.calls if c[0] is models.RiskFactorChanges)
    assert "PRIOR YEAR" in rfc_call[2]


def test_pipeline_without_prior_filing_marks_no_prior_year(tmp_path) -> None:
    filing = _write_filing(tmp_path, "current.htm", _filing_html())
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    extract_qualitative(filing, None, llm=llm)

    rfc_call = next(c for c in llm.calls if c[0] is models.RiskFactorChanges)
    assert "no prior year available" in rfc_call[2]
    assert "PRIOR YEAR" not in rfc_call[2]


def test_pipeline_reports_missing_section_without_calling_llm(tmp_path) -> None:
    # Item 1A heading absent -> risk-factor extractor should be skipped.
    html = _filing_html().replace("Item 1A. Risk Factors", "Risk Factors")
    filing = _write_filing(tmp_path, "current.htm", html)
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    assert result.risk_factor_changes.found is False
    assert result.risk_factor_changes.parsed is None
    assert result.risk_factor_changes.reason is not None
    assert all(c[0] is not models.RiskFactorChanges for c in llm.calls)


def test_pipeline_captures_llm_error_per_section(tmp_path) -> None:
    filing = _write_filing(tmp_path, "current.htm", _filing_html())
    llm = FakeLLM(error=ExtractionError("boom"))

    result = extract_qualitative(filing, None, llm=llm)

    assert result.management_tone.found is True
    assert result.management_tone.parsed is None
    assert result.management_tone.error == "boom"
    # Every section attempted despite the first failing.
    assert result.revenue_concentration.error == "boom"


def test_pipeline_skips_llm_when_no_related_party_language(tmp_path) -> None:
    filing = _write_filing(
        tmp_path, "current.htm", _filing_html(related_party=False)
    )
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    section = result.related_party
    assert section.found is True
    assert section.parsed.has_related_party_transactions is False
    assert all(c[0] is not models.RelatedPartyTransactions for c in llm.calls)


def test_pipeline_skips_llm_when_no_concentration_language(tmp_path) -> None:
    filing = _write_filing(
        tmp_path, "current.htm", _filing_html(concentration=False)
    )
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    section = result.revenue_concentration
    assert section.found is True
    assert section.parsed.customer_concentration is False
    assert all(c[0] is not models.RevenueConcentration for c in llm.calls)
