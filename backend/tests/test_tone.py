import pytest

from app.extraction import models, tone
from app.extraction.pipeline import extract_qualitative
from app.extraction.tone import extract_management_tone_by_rules, tone_metrics
from tests.test_extraction import (
    DEFAULT_RESPONSES,
    FakeLLM,
    _filing_html,
    _write_filing,
)

FILLER = "The company operates in several segments across many markets. "
NEGATIVE = (
    "Results declined as losses, impairment and weak demand caused adverse "
    "effects and delays. "
)
POSITIVE = (
    "Results improved on strong growth, record gains and robust momentum with "
    "successful innovation. "
)
HEDGED = (
    "Outcomes may vary and could depend on uncertain, volatile and "
    "unpredictable conditions, and we estimate and assume approximately so. "
)


def _text(*parts: str, filler_repeats: int = 120) -> str:
    return " ".join(parts) + " " + FILLER * filler_repeats


def test_negative_language_is_classified_negative() -> None:
    result = extract_management_tone_by_rules(_text(NEGATIVE * 40))

    assert result is not None
    assert result.overall_tone == "negative"


def test_positive_language_is_classified_optimistic() -> None:
    result = extract_management_tone_by_rules(_text(POSITIVE * 40))

    assert result is not None
    assert result.overall_tone == "optimistic"


def test_mixed_language_falls_between() -> None:
    result = extract_management_tone_by_rules(_text(POSITIVE * 20 + NEGATIVE * 30))

    assert result is not None
    assert result.overall_tone in {"balanced", "cautious"}


def test_hedging_intensity_follows_uncertainty_rate() -> None:
    plain = extract_management_tone_by_rules(_text(FILLER * 5))
    hedged = extract_management_tone_by_rules(_text(HEDGED * 40))

    assert plain is not None and hedged is not None
    assert plain.hedging_intensity == "low"
    assert hedged.hedging_intensity == "high"


def test_short_section_is_undecided() -> None:
    assert extract_management_tone_by_rules("Incorporated by reference.") is None


def test_neutral_change_words_do_not_move_tone() -> None:
    metrics = tone_metrics(
        "Revenue increased while costs decreased and expenses reduced."
    )

    assert metrics.negative_rate == 0
    assert metrics.positive_rate == 0


def test_rates_are_per_thousand_words() -> None:
    metrics = tone_metrics("losses " + "word " * 999)

    assert metrics.words == 1000
    assert metrics.negative_rate == pytest.approx(1.0)


def test_guidance_and_concern_sentences_are_extracted_verbatim() -> None:
    guidance = "We expect revenue to grow next year as new products launch."
    concern = "Impairment, losses, delays and weak demand created adverse pressure."
    result = extract_management_tone_by_rules(_text(guidance, concern))

    assert result is not None
    assert guidance in result.forward_guidance
    assert concern in result.notable_concerns


def test_summary_states_method_and_rates() -> None:
    result = extract_management_tone_by_rules(_text(NEGATIVE * 40))

    assert result is not None
    assert result.summary.startswith("Rule-based:")
    assert "per 1,000" in result.summary


def _html_with_long_mda(body: str) -> str:
    return _filing_html().replace(
        "Revenue grew and we expect", body + " Revenue grew and we expect"
    )


def test_pipeline_uses_rules_for_a_long_mda_without_calling_llm(tmp_path) -> None:
    filing = _write_filing(
        tmp_path, "current.htm", _html_with_long_mda(_text(NEGATIVE * 40))
    )
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    assert result.management_tone.method == "rules"
    assert result.management_tone.parsed.overall_tone == "negative"
    assert all(c[0] is not models.ManagementTone for c in llm.calls)


def test_pipeline_falls_back_to_llm_for_a_short_mda(tmp_path) -> None:
    filing = _write_filing(tmp_path, "current.htm", _filing_html())
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    assert result.management_tone.method == "llm"
    assert any(c[0] is models.ManagementTone for c in llm.calls)


def test_env_override_forces_llm_tone(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TENK_TONE_METHOD", "llm")
    filing = _write_filing(
        tmp_path, "current.htm", _html_with_long_mda(_text(NEGATIVE * 40))
    )
    llm = FakeLLM(responses=DEFAULT_RESPONSES)

    result = extract_qualitative(filing, None, llm=llm)

    assert result.management_tone.method == "llm"
    assert any(c[0] is models.ManagementTone for c in llm.calls)


def test_threshold_constants_are_ordered() -> None:
    assert tone.NEGATIVE_NET < tone.BALANCED_NET < tone.OPTIMISTIC_NET
    assert tone.HEDGING_MODERATE < tone.HEDGING_HIGH
