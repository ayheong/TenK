"""Governance subscore: internal control weakness, audit opinion type and
related-party transaction concern."""

from app.extraction.models import (
    GoingConcernOpinion,
    QualitativeExtraction,
    RelatedPartyTransactions,
)
from app.scoring.curves import blend
from app.scoring.models import Subscore
from app.scoring.qualitative import parsed_as, unavailable
from app.scoring.weights import SUBSCORE_WEIGHTS

_MATERIAL_WEAKNESS_RISK = 100.0
_AUDIT_OPINION_RISK = {
    "unqualified": 0.0,
    "qualified": 60.0,
    "adverse": 90.0,
    "disclaimer": 100.0,
}
_RELATED_PARTY_RISK = {"routine": 10.0, "noteworthy": 50.0, "concerning": 100.0}

_MATERIAL_WEAKNESS_WEIGHT = 0.5
_AUDIT_OPINION_WEIGHT = 0.3
_RELATED_PARTY_WEIGHT = 0.2


def compute_governance_subscore(extraction: QualitativeExtraction) -> Subscore:
    """Unavailable when neither the Item 8 / 9A opinion nor the related-party
    extraction succeeded. An opinion type of `not_found` contributes no signal."""
    opinion = parsed_as(extraction.going_concern, GoingConcernOpinion)
    related = parsed_as(extraction.related_party, RelatedPartyTransactions)
    scored: list[tuple[str, float | str, float, float, str]] = []

    if opinion is not None:
        scored.append(
            (
                "material_weakness",
                str(opinion.material_weakness),
                _MATERIAL_WEAKNESS_RISK if opinion.material_weakness else 0.0,
                _MATERIAL_WEAKNESS_WEIGHT,
                "Item 9A",
            )
        )
        if opinion.auditor_opinion_type in _AUDIT_OPINION_RISK:
            scored.append(
                (
                    "auditor_opinion",
                    opinion.auditor_opinion_type,
                    _AUDIT_OPINION_RISK[opinion.auditor_opinion_type],
                    _AUDIT_OPINION_WEIGHT,
                    "Item 8",
                )
            )

    if related is not None:
        worst = max(
            (t.concern_level for t in related.transactions),
            key=_RELATED_PARTY_RISK.__getitem__,
            default="none",
        )
        scored.append(
            (
                "related_party_concern",
                worst,
                _RELATED_PARTY_RISK.get(worst, 0.0),
                _RELATED_PARTY_WEIGHT,
                "Item 8",
            )
        )

    if not scored:
        return unavailable(
            "governance",
            "legal_governance",
            "no audit opinion or related-party extraction available",
        )

    score, signals = blend(scored, kind="qualitative")
    return Subscore(
        key="governance",
        family="legal_governance",
        score=score,
        weight=SUBSCORE_WEIGHTS["governance"],
        available=True,
        signals=signals,
    )
