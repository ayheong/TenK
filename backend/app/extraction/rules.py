"""Rule-based extraction of the audit opinion type, going-concern doubt and
material weakness from Item 8 / Item 9A text.

The language for these three signals is regular enough to match without a
model, and it is the highest-stakes input to the governance subscore. The
extractor answers only when every field is unambiguous and returns None
otherwise, so the caller can fall back to the LLM. Evidence is always a
verbatim sentence from the whitespace-normalised section text.
"""

import re
from typing import Literal

from app.extraction.models import GoingConcernOpinion

SentenceKind = Literal["affirmative", "negated", "hypothetical", "ambiguous", "ignore"]

_SENTENCE_BREAK = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“(])')
_EVIDENCE_MAX_CHARS = 600

_DOUBT = re.compile(r"substantial doubt", re.IGNORECASE)
_DOUBT_NEGATION = re.compile(
    r"\b(?:no|not|without|neither)\s+(?:\w+\s+){0,3}?"
    r"(?:substantial doubt|raise[sd]?|raising|exist\w*)",
    re.IGNORECASE,
)
_DOUBT_RESOLVED = re.compile(
    r"\b(alleviat\w*|eliminat\w*|dispel\w*|mitigat\w*|overcom\w*|overcame)\b",
    re.IGNORECASE,
)
_DOUBT_HYPOTHETICAL = re.compile(
    r"\b(could|may|might|would|should|if|whether|in the event)\b", re.IGNORECASE
)
_DOUBT_EVALUATIVE = re.compile(
    r"\b(evaluat\w*|assess\w*|determin\w*|requires?|required)\b", re.IGNORECASE
)
_DOUBT_UNRESOLVED = re.compile(
    r"\b(?:not|never|unable to)\s+(?:\w+\s+){0,3}?"
    r"(?:alleviat\w*|eliminat\w*|dispel\w*|mitigat\w*|overcom\w*)",
    re.IGNORECASE,
)
_DOUBT_GENERIC = re.compile(
    r"\ban entity\b|\bmanagement (?:should|shall)\b", re.IGNORECASE
)
_DOUBT_TEMPORAL = re.compile(r"\b(initially|previously|formerly)\b", re.IGNORECASE)

_MATERIAL_WEAKNESS = re.compile(r"material weakness", re.IGNORECASE)
_MW_BOILERPLATE = re.compile(
    r"material weakness(es)?\s+(is|are)\s+(defined as\s+)?a\s+deficiency|"
    r"risk that a material weakness exists",
    re.IGNORECASE,
)
_MW_NEGATION = re.compile(
    r"\bno\s+(?:\w+\s+){0,4}material weakness|"
    r"\bwithout\s+(?:any\s+)?material weakness|"
    r"\b(?:not|never)\s+(?:\w+\s+){0,3}?"
    r"(?:identif\w*|detect\w*|aware of|disclos\w*|have|had|has|contain\w*|"
    r"exist\w*|note\w*|found|observ\w*|discover\w*)"
    r"\s+(?:\w+\s+){0,3}?material weakness|"
    r"material weakness(?:es)?\s+(?:\w+\s+){0,3}?(?:not|never)\s+(?:\w+\s+){0,2}?"
    r"(?:identif\w*|detect\w*|exist\w*|occur\w*|found|note\w*)",
    re.IGNORECASE,
)
_MW_REMEDIATION = re.compile(r"remediat\w*", re.IGNORECASE)
_MW_HYPOTHETICAL = re.compile(r"\b(could|may|might|would|should|if)\b", re.IGNORECASE)

_ICFR = r"(?:internal control over financial reporting|ICFR)"
_ICFR_NOT_EFFECTIVE = re.compile(
    rf"{_ICFR}\b[^.]{{0,120}}?\b(?:was|were|is|are)\s+(?:not\s+effective|ineffective)|"
    r"not\s+maintained\s+(?:\w+\s+){0,2}effective\s+internal control",
    re.IGNORECASE,
)
_ICFR_EFFECTIVE = re.compile(
    rf"{_ICFR}\b[^.]{{0,120}}?\b(?:was|were|is|are)\s+effective|"
    r"maintained,?\s+in all material respects,?\s+effective\s+internal control",
    re.IGNORECASE,
)

_OPINION = re.compile(r"\bin our opinion\b", re.IGNORECASE)
_PRESENT_FAIRLY = re.compile(r"present\w*\s+fairly|fairly\s+present", re.IGNORECASE)
_ADVERSE = re.compile(r"\b(?:do|does)\s+not\s+present\s+fairly", re.IGNORECASE)
_QUALIFIED = re.compile(
    r"\bexcept\s+for\b|\bwith\s+the\s+exception\s+of\b", re.IGNORECASE
)
_DISCLAIMER = re.compile(
    r"\b(?:do|does)\s+not\s+express\s+an\s+opinion|"
    r"\bunable\s+to\s+express\s+an\s+opinion|"
    r"\bdisclaim\w*\s+(?:an\s+)?opinion",
    re.IGNORECASE,
)

OpinionType = Literal["unqualified", "qualified", "adverse", "disclaimer", "not_found"]

_OPINION_PHRASES: dict[str, str] = {
    "unqualified": "unqualified audit opinion",
    "qualified": "qualified audit opinion",
    "adverse": "adverse audit opinion",
    "disclaimer": "disclaimer of opinion",
    "not_found": "no audit opinion found in the provided text",
}


def extract_going_concern_by_rules(
    item_8_text: str | None, item_9a_text: str | None
) -> GoingConcernOpinion | None:
    """Return the opinion extraction if every field is unambiguous, else None.

    A returned `not_found` opinion type is a real answer (no opinion language
    in the text), not an undecided field."""
    sentences = _sentences(" ".join(t for t in (item_8_text, item_9a_text) if t))
    if not sentences:
        return None

    opinion = _opinion_type(sentences)
    going_concern = _going_concern(sentences)
    material_weakness = _material_weakness(sentences)
    if opinion is None or going_concern is None or material_weakness is None:
        return None

    opinion_type, opinion_evidence = opinion
    doubt, doubt_evidence = going_concern
    weakness, weakness_evidence = material_weakness
    evidence = (
        (doubt_evidence if doubt else None)
        or (weakness_evidence if weakness else None)
        or opinion_evidence
        or weakness_evidence
        or doubt_evidence
        or "No audit opinion, going-concern or internal control language found."
    )
    return GoingConcernOpinion(
        auditor_opinion_type=opinion_type,
        going_concern_doubt=doubt,
        material_weakness=weakness,
        evidence=evidence[:_EVIDENCE_MAX_CHARS],
        summary=(
            f"Rule-based: {_OPINION_PHRASES[opinion_type]}; going-concern doubt "
            f"{'expressed' if doubt else 'not expressed'}; material weakness "
            f"{'disclosed' if weakness else 'not disclosed'}."
        ),
    )


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_BREAK.split(re.sub(r"\s+", " ", text)) if s]


def _classify_doubt(sentence: str) -> SentenceKind:
    match = _DOUBT.search(sentence)
    before = sentence[: match.end()] if match else sentence
    if _DOUBT_GENERIC.search(sentence):
        return "hypothetical"
    if _DOUBT_TEMPORAL.search(sentence):
        return "ambiguous"
    if _DOUBT_UNRESOLVED.search(sentence):
        return "affirmative"
    if _DOUBT_NEGATION.search(sentence) or _DOUBT_RESOLVED.search(sentence):
        return "negated"
    if _DOUBT_HYPOTHETICAL.search(before):
        return "hypothetical"
    if _DOUBT_EVALUATIVE.search(before):
        return "ambiguous"
    return "affirmative"


def _going_concern(sentences: list[str]) -> tuple[bool, str | None] | None:
    classified = [(_classify_doubt(s), s) for s in sentences if _DOUBT.search(s)]
    kinds = {kind for kind, _ in classified}
    if "ambiguous" in kinds or ("affirmative" in kinds and "negated" in kinds):
        return None
    if "affirmative" in kinds:
        return True, next(s for kind, s in classified if kind == "affirmative")
    return False, classified[0][1] if classified else None


def _classify_weakness(sentence: str) -> SentenceKind:
    if _MW_NEGATION.search(sentence):
        return "negated"
    if _MW_BOILERPLATE.search(sentence):
        return "ignore"
    if _MW_REMEDIATION.search(sentence):
        return "ambiguous"
    match = _MATERIAL_WEAKNESS.search(sentence)
    if match and _MW_HYPOTHETICAL.search(sentence[: match.start()]):
        return "hypothetical"
    return "affirmative"


def _material_weakness(sentences: list[str]) -> tuple[bool, str | None] | None:
    classified = [
        (_classify_weakness(s), s) for s in sentences if _MATERIAL_WEAKNESS.search(s)
    ]
    affirmative = [s for kind, s in classified if kind == "affirmative"]
    not_effective = [s for s in sentences if _ICFR_NOT_EFFECTIVE.search(s)]
    effective = [s for s in sentences if _ICFR_EFFECTIVE.search(s)]

    if affirmative or not_effective:
        if effective:
            return None
        return True, (affirmative or not_effective)[0]
    if any(kind == "ambiguous" for kind, _ in classified):
        return None
    if effective:
        return False, effective[0]
    return None


def _opinion_type(sentences: list[str]) -> tuple[OpinionType, str | None] | None:
    found: list[tuple[OpinionType, str]] = []
    for sentence in sentences:
        if _DISCLAIMER.search(sentence):
            found.append(("disclaimer", sentence))
        elif _OPINION.search(sentence) and _PRESENT_FAIRLY.search(sentence):
            if _ADVERSE.search(sentence):
                found.append(("adverse", sentence))
            elif _QUALIFIED.search(sentence):
                found.append(("qualified", sentence))
            else:
                found.append(("unqualified", sentence))

    if not found:
        return "not_found", None
    kinds = {kind for kind, _ in found}
    if len(kinds) > 1:
        return None
    return found[0]
