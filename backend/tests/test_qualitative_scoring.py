import pytest

from app.extraction.models import (
    GoingConcernOpinion,
    ManagementTone,
    ParsedExtraction,
    QualitativeExtraction,
    RelatedPartyItem,
    RelatedPartyTransactions,
    RiskFactorChanges,
    RiskFactorItem,
    SectionExtraction,
)
from app.scoring.disclosure import compute_disclosure_subscore
from app.scoring.governance import compute_governance_subscore
from app.scoring.litigation import compute_litigation_subscore


def _section(
    extraction_type: str, parsed: ParsedExtraction | None
) -> SectionExtraction:
    return SectionExtraction(
        extraction_type=extraction_type,
        item_number="1A",
        found=parsed is not None,
        parsed=parsed,
    )


def _risk(category: str, severity: str) -> RiskFactorItem:
    return RiskFactorItem(
        title="t", category=category, severity_language=severity, summary="s"
    )


def _changes(
    added: list[RiskFactorItem] | None = None,
    escalated: list[RiskFactorItem] | None = None,
    net_change: str = "unchanged",
    prior_year_available: bool = True,
) -> RiskFactorChanges:
    return RiskFactorChanges(
        added=added or [],
        escalated=escalated or [],
        net_change=net_change,
        prior_year_available=prior_year_available,
        summary="s",
    )


def _opinion(
    opinion_type: str = "unqualified", material_weakness: bool = False
) -> GoingConcernOpinion:
    return GoingConcernOpinion(
        auditor_opinion_type=opinion_type,
        going_concern_doubt=False,
        material_weakness=material_weakness,
        evidence="e",
        summary="s",
    )


def _tone(overall: str = "balanced", hedging: str = "low") -> ManagementTone:
    return ManagementTone(overall_tone=overall, hedging_intensity=hedging, summary="s")


def _related(*levels: str) -> RelatedPartyTransactions:
    return RelatedPartyTransactions(
        has_related_party_transactions=bool(levels),
        transactions=[
            RelatedPartyItem(counterparty="c", nature="n", concern_level=level)
            for level in levels
        ],
        summary="s",
    )


def _extraction(
    changes: RiskFactorChanges | None = None,
    tone: ManagementTone | None = None,
    opinion: GoingConcernOpinion | None = None,
    related: RelatedPartyTransactions | None = None,
) -> QualitativeExtraction:
    return QualitativeExtraction(
        ticker="X",
        cik=1,
        accession="0000000000-24-000001",
        model_version="test",
        risk_factor_changes=_section("risk_factor_changes", changes),
        management_tone=_section("management_tone", tone),
        going_concern=_section("going_concern", opinion),
        related_party=_section("related_party", related),
        revenue_concentration=_section("revenue_concentration", None),
    )


def test_litigation_scores_only_legal_and_regulatory_changes() -> None:
    sub = compute_litigation_subscore(
        _extraction(
            changes=_changes(
                added=[_risk("legal", "elevated"), _risk("cybersecurity", "severe")],
                escalated=[_risk("regulatory", "severe")],
            )
        )
    )

    assert sub.available
    assert sub.score == pytest.approx(0.5 * 40 + 0.5 * 80)
    assert all(s.kind == "qualitative" for s in sub.signals)
    assert [s.raw_value for s in sub.signals] == [1.0, 1.0]


def test_litigation_caps_points_at_100() -> None:
    sub = compute_litigation_subscore(
        _extraction(changes=_changes(added=[_risk("legal", "severe")] * 3))
    )

    assert sub.signals[0].contribution == pytest.approx(50.0)


def test_litigation_unavailable_without_prior_year() -> None:
    sub = compute_litigation_subscore(
        _extraction(changes=_changes(prior_year_available=False))
    )

    assert not sub.available
    assert sub.reason_code == "missing_input"


def test_litigation_unavailable_when_extraction_missing() -> None:
    assert not compute_litigation_subscore(_extraction()).available


def test_governance_flags_material_weakness_and_qualified_opinion() -> None:
    sub = compute_governance_subscore(
        _extraction(opinion=_opinion("qualified", material_weakness=True))
    )

    assert sub.available
    assert sub.score == pytest.approx((0.5 * 100 + 0.3 * 60) / 0.8)


def test_governance_uses_worst_related_party_concern() -> None:
    sub = compute_governance_subscore(
        _extraction(
            opinion=_opinion(),
            related=_related("routine", "concerning", "noteworthy"),
        )
    )

    related = next(s for s in sub.signals if s.key == "related_party_concern")
    assert related.raw_value == "concerning"
    assert sub.score == pytest.approx(0.2 * 100)


def test_governance_clean_filing_scores_zero() -> None:
    sub = compute_governance_subscore(
        _extraction(opinion=_opinion(), related=_related())
    )

    assert sub.score == pytest.approx(0.0)
    assert all(s.direction == "lowers" for s in sub.signals)


def test_governance_skips_opinion_type_when_not_found() -> None:
    sub = compute_governance_subscore(_extraction(opinion=_opinion("not_found")))

    assert [s.key for s in sub.signals] == ["material_weakness"]


def test_governance_unavailable_without_inputs() -> None:
    sub = compute_governance_subscore(_extraction())

    assert not sub.available
    assert sub.reason_code == "missing_input"


def test_disclosure_blends_risk_factor_and_tone_signals() -> None:
    sub = compute_disclosure_subscore(
        _extraction(
            changes=_changes(
                added=[_risk("other", "routine")],
                escalated=[_risk("financial", "elevated")],
                net_change="expanded",
            ),
            tone=_tone("cautious", "high"),
        )
    )

    expected = 0.2 * 50 + 0.4 * 40 + 0.2 * 5 + 0.1 * 50 + 0.1 * 70
    assert sub.available
    assert sub.score == pytest.approx(expected)


def test_disclosure_falls_back_to_tone_without_prior_year() -> None:
    sub = compute_disclosure_subscore(
        _extraction(
            changes=_changes(prior_year_available=False),
            tone=_tone("negative", "high"),
        )
    )

    assert [s.key for s in sub.signals] == ["management_tone", "hedging_intensity"]
    assert sub.score == pytest.approx((0.1 * 90 + 0.1 * 70) / 0.2)


def test_disclosure_unavailable_without_inputs() -> None:
    sub = compute_disclosure_subscore(_extraction())

    assert not sub.available
    assert sub.reason_code == "missing_input"
