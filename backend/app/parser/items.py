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
