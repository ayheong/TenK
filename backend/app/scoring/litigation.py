"""Litigation/regulatory subscore: new and escalated legal and regulatory risk
factors in Item 1A versus the prior year."""

from app.extraction.models import QualitativeExtraction, RiskFactorChanges
from app.scoring.curves import blend
from app.scoring.models import Subscore
from app.scoring.qualitative import parsed_as, severity_points, unavailable
from app.scoring.weights import SUBSCORE_WEIGHTS

_LEGAL_CATEGORIES = {"legal", "regulatory"}

_ADDED_POINTS = {"routine": 15.0, "elevated": 40.0, "severe": 70.0}
_ESCALATED_POINTS = {"routine": 20.0, "elevated": 50.0, "severe": 80.0}

_ADDED_WEIGHT = 0.5
_ESCALATED_WEIGHT = 0.5


def compute_litigation_subscore(extraction: QualitativeExtraction) -> Subscore:
    """Scores only what changed year over year, so steady, long-standing
    litigation exposure is not captured. Unavailable without a successful Item
    1A comparison against a prior-year filing."""
    changes = parsed_as(extraction.risk_factor_changes, RiskFactorChanges)
    if changes is None:
        return unavailable(
            "litigation_regulatory",
            "legal_governance",
            "Item 1A risk factor changes unavailable",
        )
    if not changes.prior_year_available:
        return unavailable(
            "litigation_regulatory",
            "legal_governance",
            "no prior-year Item 1A to compare against",
        )

    added = [
        i.severity_language for i in changes.added if i.category in _LEGAL_CATEGORIES
    ]
    escalated = [
        i.severity_language
        for i in changes.escalated
        if i.category in _LEGAL_CATEGORIES
    ]
    score, signals = blend(
        [
            (
                "legal_regulatory_added",
                float(len(added)),
                severity_points(added, _ADDED_POINTS),
                _ADDED_WEIGHT,
                "Item 1A",
            ),
            (
                "legal_regulatory_escalated",
                float(len(escalated)),
                severity_points(escalated, _ESCALATED_POINTS),
                _ESCALATED_WEIGHT,
                "Item 1A",
            ),
        ],
        kind="qualitative",
    )
    return Subscore(
        key="litigation_regulatory",
        family="legal_governance",
        score=score,
        weight=SUBSCORE_WEIGHTS["litigation_regulatory"],
        available=True,
        signals=signals,
    )
