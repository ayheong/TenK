# Layer 2 orchestration: cached 10-K HTML -> QualitativeExtraction.
#
# For each target section: locate it with the Item parser, narrow big
# sections to just the relevant text with keyword anchoring, then run the
# matching LLM extractor. A section the parser can't find is recorded
# found=False with no LLM call. A section found but whose LLM call
# fails/refuses is recorded found=True with `error` set — one bad section
# never sinks the rest of the filing.

from pathlib import Path

from app.edgar.models import FilingRecord
from app.extraction import extractors, models
from app.extraction.llm import ExtractionError, LLMClient
from app.parser.anchors import extract_keyword_anchored_text
from app.parser.items import extract_items
from app.parser.models import ItemSection

# Sections above this many characters are truncated before going to the
# LLM. Item 1A / Item 7 can run past this on the largest filers; the
# opening is where the substantive disclosure lives.
MAX_SECTION_CHARS = 120_000

# When keyword anchoring inside a large section fails, fall back to this
# many chars from its start (audit report, ICFR conclusion, and customer
# discussion all sit near the top of their sections).
ANCHOR_FALLBACK_CHARS = 20_000

RELATED_PARTY_KEYWORDS = [
    "related party",
    "related-party",
    "related parties",
    "affiliated entity",
    "transactions with affiliates",
]
GOING_CONCERN_KEYWORDS = [
    "going concern",
    "substantial doubt",
    "material weakness",
    "adverse opinion",
    "disclaimer of opinion",
    "basis for opinion",
    "opinion on the financial statements",
    "internal control over financial reporting",
]
CONCENTRATION_KEYWORDS = [
    "concentration",
    "one customer",
    "single customer",
    "significant customer",
    "major customer",
    "accounted for",
    "% of net revenue",
    "% of total revenue",
    "% of revenue",
]

_TARGET_ITEMS = ["1", "1A", "7", "8", "9A"]


def extract_qualitative(
    filing: FilingRecord,
    prior_filing: FilingRecord | None = None,
    *,
    llm: LLMClient | None = None,
) -> models.QualitativeExtraction:
    """Run every Layer 2 extractor against one filing. `prior_filing`, if
    given, supplies the prior-year Item 1A for the risk-factor diff."""
    llm = llm or LLMClient()

    items = extract_items(_read(filing.cached_path), _TARGET_ITEMS)
    prior_1a = _prior_item_1a(prior_filing)

    return models.QualitativeExtraction(
        ticker=filing.ticker,
        cik=filing.cik,
        accession=filing.accession,
        prior_accession=filing.prior_accession,
        model_version=llm.model,
        risk_factor_changes=_run_risk_factor_changes(llm, items["1A"], prior_1a),
        management_tone=_run_management_tone(llm, items["7"]),
        going_concern=_run_going_concern(llm, items["8"], items["9A"]),
        related_party=_run_related_party(llm, items["8"]),
        revenue_concentration=_run_revenue_concentration(llm, items["1"], items["7"]),
    )


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _prior_item_1a(prior_filing: FilingRecord | None) -> str | None:
    if prior_filing is None:
        return None
    section = extract_items(_read(prior_filing.cached_path), ["1A"])["1A"]
    return section.text if section.found else None


def _section(
    extraction_type: models.ExtractionType,
    item_number: str,
    *,
    found: bool,
    parsed: models.ParsedExtraction | None = None,
    error: str | None = None,
    reason: str | None = None,
    source_chars: int = 0,
) -> models.SectionExtraction:
    return models.SectionExtraction(
        extraction_type=extraction_type,
        item_number=item_number,
        found=found,
        parsed=parsed,
        error=error,
        reason=reason,
        source_chars=source_chars,
    )


def _guarded(extraction_type, item_number, source_chars, reason, call):
    """Run an LLM extractor, capturing content-level failures as `error`."""
    try:
        parsed = call()
    except ExtractionError as exc:
        return _section(
            extraction_type,
            item_number,
            found=True,
            error=str(exc),
            source_chars=source_chars,
        )
    return _section(
        extraction_type,
        item_number,
        found=True,
        parsed=parsed,
        reason=reason,
        source_chars=source_chars,
    )


def _truncate(text: str) -> tuple[str, str | None]:
    if len(text) <= MAX_SECTION_CHARS:
        return text, None
    return text[:MAX_SECTION_CHARS], "section text truncated to fit context window"


def _run_risk_factor_changes(
    llm: LLMClient, item_1a: ItemSection, prior_1a: str | None
) -> models.SectionExtraction:
    if not item_1a.found:
        return _section("risk_factor_changes", "1A", found=False, reason=item_1a.reason)

    current, note = _truncate(item_1a.text)
    prior = prior_1a[:MAX_SECTION_CHARS] if prior_1a else None
    source_chars = len(current) + (len(prior) if prior else 0)
    return _guarded(
        "risk_factor_changes",
        "1A",
        source_chars,
        note,
        lambda: extractors.extract_risk_factor_changes(llm, current, prior),
    )


def _run_management_tone(
    llm: LLMClient, item_7: ItemSection
) -> models.SectionExtraction:
    if not item_7.found:
        return _section("management_tone", "7", found=False, reason=item_7.reason)

    text, note = _truncate(item_7.text)
    return _guarded(
        "management_tone",
        "7",
        len(text),
        note,
        lambda: extractors.extract_management_tone(llm, text),
    )


def _run_going_concern(
    llm: LLMClient, item_8: ItemSection, item_9a: ItemSection
) -> models.SectionExtraction:
    parts: list[str] = []
    if item_8.found:
        parts.append(
            "=== ITEM 8 (auditor's report / financial statements) ===\n"
            + _narrow(item_8.text, GOING_CONCERN_KEYWORDS)
        )
    if item_9a.found:
        parts.append(
            "=== ITEM 9A (controls and procedures) ===\n"
            + _narrow(item_9a.text, GOING_CONCERN_KEYWORDS)
        )

    if not parts:
        return _section(
            "going_concern",
            "8",
            found=False,
            reason="neither Item 8 nor Item 9A was located in the filing",
        )

    text = "\n\n".join(parts)
    return _guarded(
        "going_concern",
        "8",
        len(text),
        None,
        lambda: extractors.extract_going_concern(llm, text),
    )


def _run_related_party(
    llm: LLMClient, item_8: ItemSection
) -> models.SectionExtraction:
    if not item_8.found:
        return _section("related_party", "8", found=False, reason=item_8.reason)

    anchored = extract_keyword_anchored_text(item_8.text, RELATED_PARTY_KEYWORDS)
    if not anchored.found:
        # No related-party language anywhere in Item 8 — an honest
        # structured negative, no LLM call needed.
        return _section(
            "related_party",
            "8",
            found=True,
            parsed=models.RelatedPartyTransactions(
                has_related_party_transactions=False,
                transactions=[],
                summary="No related-party transaction disclosure found in Item 8.",
            ),
            reason="no related-party keyword match in Item 8",
        )

    return _guarded(
        "related_party",
        "8",
        len(anchored.text),
        None,
        lambda: extractors.extract_related_party(llm, anchored.text),
    )


def _run_revenue_concentration(
    llm: LLMClient, item_1: ItemSection, item_7: ItemSection
) -> models.SectionExtraction:
    chunks: list[str] = []
    for section, label in ((item_1, "ITEM 1 (Business)"), (item_7, "ITEM 7 (MD&A)")):
        if not section.found:
            continue
        anchored = extract_keyword_anchored_text(section.text, CONCENTRATION_KEYWORDS)
        if anchored.found:
            chunks.append(f"=== {label} ===\n{anchored.text}")

    if not chunks:
        return _section(
            "revenue_concentration",
            "1",
            found=True,
            parsed=models.RevenueConcentration(
                customer_concentration=False,
                named_customers=[],
                summary=(
                    "No customer or revenue concentration language found in "
                    "Item 1 or Item 7."
                ),
            ),
            reason="no concentration keyword match in Item 1 or Item 7",
        )

    text = "\n\n".join(chunks)
    return _guarded(
        "revenue_concentration",
        "1",
        len(text),
        None,
        lambda: extractors.extract_revenue_concentration(llm, text),
    )


def _narrow(text: str, keywords: list[str]) -> str:
    """Keyword-anchor a large section; fall back to its opening if no
    keyword matches, and cap the result."""
    anchored = extract_keyword_anchored_text(text, keywords)
    narrowed = anchored.text if anchored.found else text[:ANCHOR_FALLBACK_CHARS]
    return narrowed[:MAX_SECTION_CHARS]
