import html
import re

from app.parser.models import ItemSection

# Every Item number a 10-K can contain, in filing order. Used to (a) find
# where the table of contents ends (it lists this whole sequence, tightly
# packed, before any real section content appears) and (b) know which item
# closes out a section's boundary.
CANONICAL_ORDER = [
    "1", "1A", "1B", "1C", "2", "3", "4", "5", "6", "7", "7A", "8", "9",
    "9A", "9B", "9C", "10", "11", "12", "13", "14", "15", "16",
]

# A gap this large between two consecutive heading matches signals we've
# left the table of contents (where entries sit within ~250 characters of
# each other) and entered real body content.
TOC_GAP_THRESHOLD = 400

# A "found" section shorter than this is more likely a stray heading-only
# match than real section content.
MIN_SECTION_LENGTH = 200

# Anchored to the start of a line (block), not just anywhere in the text.
# Real headings almost always open their own paragraph/cell/div; a plain
# substring match would also hit cross-references embedded mid-sentence
# (e.g. "...appearing under Item 9A." inside an auditor's report), which
# would silently truncate the real section at the wrong point.
ITEM_PATTERN = re.compile(r"(?m)^\s*Item\s+(\d{1,2}[A-Za-z]?)\.", re.IGNORECASE)

# Some filers (e.g. NVIDIA, JPMorgan, Chevron) satisfy Item 8 with a short
# cross-reference notice ("set forth on page 162", "incorporated by
# reference", "see the Financial Table of Contents") instead of placing
# the financial statements at that point in the document — the real
# statements sit elsewhere, sometimes inside a later Item (e.g. Item 15),
# sometimes in an unlabeled block with no Item number of its own. A found
# Item 8 section this short is essentially always such a stub — real
# financial statements run tens of thousands of characters at minimum —
# regardless of the exact wording used, so length alone is the trigger.
ITEM_8_REDIRECT_MAX_LENGTH = 1500

# The heading that opens the audited financial statements block. Every
# filer's index-of-financial-statements also contains this exact phrase,
# so the heading text alone can't tell a real section start from an index
# entry — but what immediately follows can: an index entry is followed by
# a bare page number (same line or its own line, filer-dependent), while
# the real heading is followed by the report's actual prose.
AUDITOR_REPORT_HEADING = re.compile(
    r"(?m)^\s*Report of Independent Registered Public Accounting Firm\b.*$",
    re.IGNORECASE,
)
PAGE_NUMBER_LINE = re.compile(r"^[\d\s\-–—]+$")

_BLOCK_END_TAGS = re.compile(r"</(p|div|td|tr|li|h[1-6])\s*>", re.IGNORECASE)
_BR_TAG = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _to_text(filing_html: str) -> str:
    """Flatten filing HTML to plain text, preserving block-level (p, div,
    td, tr, li, h1-6, br) boundaries as newlines so a heading that opens
    its own block stays distinguishable from a mid-sentence mention."""
    marked = _BR_TAG.sub("\n", _BLOCK_END_TAGS.sub("\n", filing_html))
    text = html.unescape(re.sub(r"<[^>]+>", " ", marked))
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(lines)


def _find_matches(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1).upper()) for m in ITEM_PATTERN.finditer(text)]


def _body_matches(matches: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop the table-of-contents cluster: everything up to and including
    the first large gap between consecutive matches."""
    for i in range(len(matches) - 1):
        gap = matches[i + 1][0] - matches[i][0]
        if gap >= TOC_GAP_THRESHOLD:
            return matches[i + 1 :]
    return []


def extract_items(
    filing_html: str, item_numbers: list[str]
) -> dict[str, ItemSection]:
    """Best-effort extraction of raw text for each requested Item number.

    Real 10-K section-heading formatting varies a lot by filing agent (some
    embed "Item 7." directly in body text, some use no period, some repeat
    a running page-header). This only trusts a heading that opens its own
    block, outside the table of contents; anything it can't confidently
    locate is reported as not found rather than guessed at.
    """
    text = _to_text(filing_html)
    body = _body_matches(_find_matches(text))
    body_keys = [key for _, key in body]

    return {
        item_number.upper(): _extract_one(item_number.upper(), body, body_keys, text)
        for item_number in item_numbers
    }


def _extract_one(
    key: str, body: list[tuple[int, str]], body_keys: list[str], text: str
) -> ItemSection:
    if key not in body_keys:
        return ItemSection(
            item_number=key,
            found=False,
            reason="no confident heading match found in filing body",
        )

    start_index = body_keys.index(key)
    start_pos = body[start_index][0]
    end_pos = _next_boundary(key, body, start_index)
    section_text = text[start_pos:end_pos].strip()

    if key == "8" and len(section_text) < ITEM_8_REDIRECT_MAX_LENGTH:
        redirected = _resolve_item_8_redirect(body, start_pos, text)
        if redirected is not None:
            return redirected

    if len(section_text) < MIN_SECTION_LENGTH:
        return ItemSection(
            item_number=key,
            found=False,
            reason=(
                f"matched heading but only {len(section_text)} chars followed "
                "before the next heading — likely a stray match, not the "
                "real section"
            ),
        )

    return ItemSection(item_number=key, found=True, text=section_text)


def _resolve_item_8_redirect(
    body: list[tuple[int, str]], item_8_start: int, text: str
) -> ItemSection | None:
    """Some filers satisfy Item 8 with a short cross-reference notice and
    place the actual financial statements elsewhere in the document —
    not necessarily inside another Item's boundary (some sit in an
    unlabeled block ahead of Item 15, some inside Item 15 itself).
    Search forward from Item 8's heading for the real opening of the
    audited financial statements, distinguishing it from the (also
    present) index-of-financial-statements entry by what follows it: a
    bare page number for the index, real prose for the actual report.
    Slices to the next Item heading found after that point, or to the
    end of the filing if none follows. Returns None if no such heading
    can be confidently located — the caller falls back to the (honest,
    if unhelpful) redirect notice in that case."""
    search_from = item_8_start
    while True:
        match = AUDITOR_REPORT_HEADING.search(text, search_from)
        if match is None:
            return None

        rest = text[match.end():]
        next_line = next((line for line in rest.split("\n") if line.strip()), "")
        if not PAGE_NUMBER_LINE.match(next_line.strip()):
            break
        search_from = match.end()

    end_pos = next((pos for pos, _ in body if pos > match.start()), None)
    financials_text = text[match.start():end_pos].strip()
    if len(financials_text) < MIN_SECTION_LENGTH:
        return None

    return ItemSection(
        item_number="8",
        found=True,
        text=financials_text,
        reason=(
            "Item 8 body was a short cross-reference notice; the actual "
            "financial statements are located elsewhere in the filing — "
            "text below is sourced from there."
        ),
    )


def _next_boundary(
    key: str, body: list[tuple[int, str]], start_index: int
) -> int | None:
    """Position of the next *different*, later canonical item after `key`,
    or None (slices to end of text) if none follows."""
    if key not in CANONICAL_ORDER:
        return None
    key_rank = CANONICAL_ORDER.index(key)
    for pos, candidate in body[start_index + 1 :]:
        if candidate in CANONICAL_ORDER and CANONICAL_ORDER.index(candidate) > key_rank:
            return pos
    return None
