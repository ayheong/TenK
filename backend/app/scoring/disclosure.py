"""Disclosure-change subscore: risk-factor language escalation versus the prior
year, plus management tone and hedging."""

from app.extraction.models import (
    ManagementTone,
    QualitativeExtraction,
    RiskFactorChanges,
)
from app.scoring.curves import blend
from app.scoring.models import Subscore
from app.scoring.qualitative import parsed_as, severity_points, unavailable
from app.scoring.weights import SUBSCORE_WEIGHTS

_NET_CHANGE_RISK = {"reduced": 0.0, "unchanged": 10.0, "expanded": 50.0}
_ESCALATED_POINTS = {"routine": 15.0, "elevated": 40.0, "severe": 70.0}
_ADDED_POINTS = {"routine": 5.0, "elevated": 25.0, "severe": 60.0}
_TONE_RISK = {"optimistic": 0.0, "balanced": 15.0, "cautious": 50.0, "negative": 90.0}
_HEDGING_RISK = {"low": 0.0, "moderate": 30.0, "high": 70.0}

_NET_CHANGE_WEIGHT = 0.2
_ESCALATED_WEIGHT = 0.4
_ADDED_WEIGHT = 0.2
_TONE_WEIGHT = 0.1
_HEDGING_WEIGHT = 0.1


def compute_disclosure_subscore(extraction: QualitativeExtraction) -> Subscore:
    """Year-over-year risk-factor signals need a successful Item 1A comparison
    against a prior-year filing; management tone does not. Unavailable when
    neither is present."""
    changes = parsed_as(extraction.risk_factor_changes, RiskFactorChanges)
    tone = parsed_as(extraction.management_tone, ManagementTone)
    scored: list[tuple[str, float | str, float, float, str]] = []

    if changes is not None and changes.prior_year_available:
        escalated = [i.severity_language for i in changes.escalated]
        added = [i.severity_language for i in changes.added]
        scored += [
            (
                "risk_factor_net_change",
                changes.net_change,
                _NET_CHANGE_RISK[changes.net_change],
                _NET_CHANGE_WEIGHT,
                "Item 1A",
            ),
            (
                "risk_factors_escalated",
                float(len(escalated)),
                severity_points(escalated, _ESCALATED_POINTS),
                _ESCALATED_WEIGHT,
                "Item 1A",
            ),
            (
                "risk_factors_added",
                float(len(added)),
                severity_points(added, _ADDED_POINTS),
                _ADDED_WEIGHT,
                "Item 1A",
            ),
        ]

    if tone is not None:
        scored += [
            (
                "management_tone",
                tone.overall_tone,
                _TONE_RISK[tone.overall_tone],
                _TONE_WEIGHT,
                "Item 7",
            ),
            (
                "hedging_intensity",
                tone.hedging_intensity,
                _HEDGING_RISK[tone.hedging_intensity],
                _HEDGING_WEIGHT,
                "Item 7",
            ),
        ]

    if not scored:
        return unavailable(
            "disclosure_change",
            "disclosure",
            "no prior-year Item 1A comparison or Item 7 tone available",
        )

    score, signals = blend(scored, kind="qualitative")
    return Subscore(
        key="disclosure_change",
        family="disclosure",
        score=score,
        weight=SUBSCORE_WEIGHTS["disclosure_change"],
        available=True,
        signals=signals,
    )
