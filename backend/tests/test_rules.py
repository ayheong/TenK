import re

import pytest

from app.extraction.rules import extract_going_concern_by_rules

CLEAN_OPINION = (
    "In our opinion, the financial statements present fairly, in all material "
    "respects, the financial position of the Company in conformity with GAAP."
)
ICFR_EFFECTIVE = (
    "Management concluded that its internal control over financial reporting "
    "was effective as of December 31, 2025."
)
ICFR_NOT_EFFECTIVE = (
    "Management concluded that the Company's internal control over financial "
    "reporting was not effective as of December 31, 2025 due to the material "
    "weakness discussed below."
)


def _extract(*sentences: str):
    return extract_going_concern_by_rules(" ".join(sentences), None)


def test_clean_large_filer_is_decided_with_no_findings() -> None:
    result = _extract(
        CLEAN_OPINION,
        "Our audit included assessing the risk that a material weakness exists.",
        ICFR_EFFECTIVE,
    )

    assert result is not None
    assert result.auditor_opinion_type == "unqualified"
    assert not result.going_concern_doubt
    assert not result.material_weakness


def test_material_weakness_definition_is_not_a_finding() -> None:
    result = _extract(
        CLEAN_OPINION,
        "A material weakness is a deficiency in internal control over financial "
        "reporting such that there is a reasonable possibility of misstatement.",
        ICFR_EFFECTIVE,
    )

    assert result is not None
    assert not result.material_weakness


def test_not_effective_conclusion_flags_material_weakness() -> None:
    result = _extract(CLEAN_OPINION, ICFR_NOT_EFFECTIVE)

    assert result is not None
    assert result.material_weakness
    assert "was not effective" in result.evidence


def test_identified_material_weakness_is_flagged() -> None:
    result = _extract(
        CLEAN_OPINION,
        "As a result of the material weakness, our disclosure controls were not "
        "effective.",
        "We identified a material weakness related to segregation of duties.",
    )

    assert result is not None
    assert result.material_weakness


@pytest.mark.parametrize(
    "sentence",
    [
        "We did not identify any material weaknesses.",
        "There were no significant deficiencies or material weaknesses.",
        "Management concluded there were no material weakness at year end.",
        "A material weakness has not been identified.",
        "The Company did not have a material weakness.",
    ],
)
def test_negated_material_weakness_is_not_flagged(sentence: str) -> None:
    result = _extract(CLEAN_OPINION, sentence, ICFR_EFFECTIVE)

    assert result is not None
    assert not result.material_weakness


def test_remediated_weakness_is_undecided() -> None:
    result = _extract(
        CLEAN_OPINION,
        "The previously identified material weakness was remediated.",
        ICFR_EFFECTIVE,
    )

    assert result is None


def test_conflicting_effective_and_not_effective_is_undecided() -> None:
    assert _extract(CLEAN_OPINION, ICFR_EFFECTIVE, ICFR_NOT_EFFECTIVE) is None


def test_no_internal_control_conclusion_is_undecided() -> None:
    assert _extract(CLEAN_OPINION) is None


def test_going_concern_doubt_is_flagged() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "These conditions raise substantial doubt about the Company's ability to "
        "continue as a going concern.",
    )

    assert result is not None
    assert result.going_concern_doubt
    assert "raise substantial doubt" in result.evidence


def test_plans_that_do_not_alleviate_doubt_still_count_as_doubt() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "Management's plans do not alleviate the substantial doubt about the "
        "Company's ability to continue as a going concern.",
    )

    assert result is not None
    assert result.going_concern_doubt


def test_resolved_doubt_is_not_flagged() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "Management concluded there is no substantial doubt about the Company's "
        "ability to continue as a going concern.",
    )

    assert result is not None
    assert not result.going_concern_doubt


def test_accounting_standard_text_is_not_a_finding() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "Substantial doubt about an entity's ability to continue as a going "
        "concern exists when relevant conditions indicate it is probable the "
        "entity will be unable to meet its obligations.",
        "Management should evaluate whether there are conditions that raise "
        "substantial doubt about the entity's ability to continue.",
    )

    assert result is not None
    assert not result.going_concern_doubt


def test_doubt_raised_then_alleviated_is_undecided() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "These conditions initially raised substantial doubt about the Company's "
        "ability to continue as a going concern.",
        "Management determined the substantial doubt has been alleviated.",
    )

    assert result is None


def test_doubt_with_evaluative_wording_is_undecided() -> None:
    result = _extract(
        CLEAN_OPINION,
        ICFR_EFFECTIVE,
        "Management evaluated the conditions and concluded they raise substantial "
        "doubt about the Company's ability to continue as a going concern.",
    )

    assert result is None


@pytest.mark.parametrize(
    ("opinion", "expected"),
    [
        (
            "In our opinion, except for the effects of the matter described above, "
            "the financial statements present fairly, in all material respects, "
            "the financial position.",
            "qualified",
        ),
        (
            "In our opinion, the financial statements do not present fairly, in "
            "all material respects, the financial position.",
            "adverse",
        ),
        (
            "We do not express an opinion on the financial statements.",
            "disclaimer",
        ),
    ],
)
def test_non_standard_opinion_types(opinion: str, expected: str) -> None:
    result = _extract(opinion, ICFR_EFFECTIVE)

    assert result is not None
    assert result.auditor_opinion_type == expected


def test_missing_opinion_is_a_decided_not_found() -> None:
    result = _extract(ICFR_EFFECTIVE)

    assert result is not None
    assert result.auditor_opinion_type == "not_found"


def test_conflicting_opinions_are_undecided() -> None:
    result = _extract(
        CLEAN_OPINION,
        "In our opinion, the financial statements do not present fairly, in all "
        "material respects, the financial position.",
        ICFR_EFFECTIVE,
    )

    assert result is None


def test_empty_text_is_undecided() -> None:
    assert extract_going_concern_by_rules(None, None) is None
    assert extract_going_concern_by_rules("", "  ") is None


def test_evidence_is_verbatim_from_normalised_source() -> None:
    text = (
        "Management   concluded that its internal control over financial\n"
        "reporting was not effective.  We identified a material weakness."
    )

    result = extract_going_concern_by_rules(text, None)

    assert result is not None
    assert result.evidence in re.sub(r"\s+", " ", text)


def test_item_9a_text_is_combined_with_item_8() -> None:
    result = extract_going_concern_by_rules(CLEAN_OPINION, ICFR_NOT_EFFECTIVE)

    assert result is not None
    assert result.material_weakness
