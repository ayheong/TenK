"""Shared helpers for subscores built from Layer 2 qualitative extractions."""

from typing import TypeVar

from pydantic import BaseModel

from app.extraction.models import SectionExtraction
from app.scoring.models import Subscore, SubscoreFamily, SubscoreKey
from app.scoring.weights import SUBSCORE_WEIGHTS

T = TypeVar("T", bound=BaseModel)


def parsed_as(section: SectionExtraction, model: type[T]) -> T | None:
    """The section's parsed result if it is a successful `model`, else None."""
    return section.parsed if isinstance(section.parsed, model) else None


def unavailable(key: SubscoreKey, family: SubscoreFamily, reason: str) -> Subscore:
    return Subscore(
        key=key,
        family=family,
        score=0.0,
        weight=SUBSCORE_WEIGHTS[key],
        available=False,
        reason_code="missing_input",
        reason=reason,
    )


def severity_points(severities: list[str], points: dict[str, float]) -> float:
    """Sum per-item points for each severity label, capped at 100."""
    return min(100.0, sum(points[severity] for severity in severities))
