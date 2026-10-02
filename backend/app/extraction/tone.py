"""Rule-based management tone and hedging from Item 7 (MD&A).

Dictionary method in the style of Loughran and McDonald: count words from
finance-specific negative, positive and uncertainty lists and normalise by
section length. The lists here are small and hand-written for this project,
not the published word lists, and the thresholds are calibrated by eye against
a handful of large filers. Treat the output as a coarse signal, not a
measurement. Neutral change words ("increased", "decreased", "reduced") are
deliberately left out because their sentiment depends on what changed.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.extraction.models import ManagementTone

MIN_WORDS = 1000
MAX_EXAMPLES = 5
_EXAMPLE_MAX_CHARS = 300

_NEGATIVE_STEMS = (
    r"declin\w*",
    r"loss(?:es)?",
    r"impair\w*",
    r"advers\w*",
    r"weak\w*",
    r"deteriorat\w*",
    r"difficult\w*",
    r"unfavorabl\w*",
    r"default\w*",
    r"restructur\w*",
    r"shortfall\w*",
    r"downturn\w*",
    r"slowdown\w*",
    r"negativ\w*",
    r"fail\w*",
    r"harm\w*",
    r"challeng\w*",
    r"pressure\w*",
    r"headwind\w*",
    r"disrupt\w*",
    r"write-?downs?",
    r"clos(?:ure|ures)",
    r"terminat\w*",
    r"delay\w*",
    r"inabilit\w*",
    r"unable",
    r"worsen\w*",
    r"lawsuit\w*",
    r"litigation",
    r"penalt\w*",
    r"investigat\w*",
    r"cancel\w*",
    r"insolven\w*",
    r"bankrupt\w*",
    r"distress\w*",
    r"violat\w*",
    r"breach\w*",
    r"deficien\w*",
    r"unprofitab\w*",
    r"layoff\w*",
    r"curtail\w*",
    r"substantial doubt",
    r"going concern",
)
_POSITIVE_STEMS = (
    r"improv\w*",
    r"strong\w*",
    r"strength\w*",
    r"record",
    r"growth",
    r"grew",
    r"growing",
    r"favorabl\w*",
    r"benefit\w*",
    r"success\w*",
    r"achiev\w*",
    r"outperform\w*",
    r"momentum",
    r"robust",
    r"gain\w*",
    r"profitab\w*",
    r"expan\w*",
    r"opportunit\w*",
    r"innovat\w*",
    r"leading",
    r"exceed\w*",
    r"accelerat\w*",
    r"enhanc\w*",
    r"resilien\w*",
)
_UNCERTAIN_STEMS = (
    r"may",
    r"might",
    r"could",
    r"uncertain\w*",
    r"approximately",
    r"believe\w*",
    r"anticipat\w*",
    r"estimat\w*",
    r"depend\w*",
    r"contingen\w*",
    r"possib\w*",
    r"potential\w*",
    r"probabl\w*",
    r"appear\w*",
    r"assum\w*",
    r"volatil\w*",
    r"fluctuat\w*",
    r"unpredictab\w*",
    r"unknown",
    r"variab\w*",
)

# Net tone (positive minus negative words per 1,000) and uncertainty rate
# cut-offs. Calibrated by eye on large-filer MD&A text; see the research note.
OPTIMISTIC_NET = 6.0
BALANCED_NET = 0.0
NEGATIVE_NET = -6.0
HEDGING_HIGH = 16.0
HEDGING_MODERATE = 12.0

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE_BREAK = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"“(])')
_GUIDANCE = re.compile(
    r"\b(?:we|the company|management)\s+(?:currently\s+|also\s+)?"
    r"(?:expect|anticipate|project|forecast|plan to|intend to)\w*\b",
    re.IGNORECASE,
)
_FORWARD = re.compile(
    r"\b(?:will|next (?:year|fiscal)|fiscal 20\d\d|20\d\d|future|coming|"
    r"continue|going forward)\b",
    re.IGNORECASE,
)

Tone = Literal["optimistic", "balanced", "cautious", "negative"]
Hedging = Literal["low", "moderate", "high"]


def _compile(stems: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(stems) + r")\b", re.IGNORECASE)


_NEGATIVE = _compile(_NEGATIVE_STEMS)
_POSITIVE = _compile(_POSITIVE_STEMS)
_UNCERTAIN = _compile(_UNCERTAIN_STEMS)


@dataclass(frozen=True)
class ToneMetrics:
    words: int
    negative_rate: float
    positive_rate: float
    uncertainty_rate: float

    @property
    def net_tone(self) -> float:
        return self.positive_rate - self.negative_rate


def tone_metrics(text: str) -> ToneMetrics:
    """Word-list hit rates per 1,000 words."""
    words = len(_WORD.findall(text))
    scale = 1000 / words if words else 0.0
    return ToneMetrics(
        words=words,
        negative_rate=len(_NEGATIVE.findall(text)) * scale,
        positive_rate=len(_POSITIVE.findall(text)) * scale,
        uncertainty_rate=len(_UNCERTAIN.findall(text)) * scale,
    )


def _overall_tone(net_tone: float) -> Tone:
    if net_tone >= OPTIMISTIC_NET:
        return "optimistic"
    if net_tone >= BALANCED_NET:
        return "balanced"
    if net_tone >= NEGATIVE_NET:
        return "cautious"
    return "negative"


def _hedging(uncertainty_rate: float) -> Hedging:
    if uncertainty_rate >= HEDGING_HIGH:
        return "high"
    if uncertainty_rate >= HEDGING_MODERATE:
        return "moderate"
    return "low"


def _guidance_sentences(sentences: list[str]) -> list[str]:
    return [s for s in sentences if _GUIDANCE.search(s) and _FORWARD.search(s)][
        :MAX_EXAMPLES
    ]


def _concern_sentences(sentences: list[str]) -> list[str]:
    scored = [(len(_NEGATIVE.findall(s)), i, s) for i, s in enumerate(sentences)]
    top = sorted((t for t in scored if t[0] >= 3), key=lambda t: (-t[0], t[1]))
    return [s for _, _, s in top[:MAX_EXAMPLES]]


def extract_management_tone_by_rules(item_7_text: str) -> ManagementTone | None:
    """Tone and hedging from word-list rates. Returns None for a section too
    short to measure, such as an Item 7 that only incorporates the annual
    report by reference."""
    metrics = tone_metrics(item_7_text)
    if metrics.words < MIN_WORDS:
        return None

    sentences = [
        s[:_EXAMPLE_MAX_CHARS]
        for s in _SENTENCE_BREAK.split(re.sub(r"\s+", " ", item_7_text))
    ]
    tone = _overall_tone(metrics.net_tone)
    hedging = _hedging(metrics.uncertainty_rate)
    return ManagementTone(
        overall_tone=tone,
        hedging_intensity=hedging,
        forward_guidance=_guidance_sentences(sentences),
        notable_concerns=_concern_sentences(sentences),
        summary=(
            f"Rule-based: {tone} tone (net {metrics.net_tone:+.1f} per 1,000 "
            f"words), {hedging} hedging ({metrics.uncertainty_rate:.1f} "
            "uncertainty words per 1,000)."
        ),
    )
