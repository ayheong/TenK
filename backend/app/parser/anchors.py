import re

from app.parser.models import KeywordAnchoredText

# Chars of context kept before/after each keyword match. Targeted content
# (a footnote, a callout) is typically a paragraph or two; asymmetric
# because the anchor phrase usually opens the relevant text rather than
# sitting in the middle of it.
CONTEXT_BEFORE = 500
CONTEXT_AFTER = 2500

# Windows separated by less than this are merged into one excerpt instead
# of producing separate, near-duplicate chunks.
MERGE_GAP = 300


def extract_keyword_anchored_text(
    text: str,
    keywords: list[str],
    context_before: int = CONTEXT_BEFORE,
    context_after: int = CONTEXT_AFTER,
) -> KeywordAnchoredText:
    """Pull just the text around keyword matches out of a large section,
    instead of sending the whole section to an LLM.

    For content that's a small part of a much larger section — e.g. a
    related-party-transactions footnote inside Item 8's full financial
    statements. Returns found=False (not an empty excerpt) when no
    keyword appears anywhere: some filers describe the content as
    incorporated by reference elsewhere rather than inline, and that's a
    real "not here" rather than a match with zero content.
    """
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    matches = list(pattern.finditer(text))

    if not matches:
        return KeywordAnchoredText(
            keywords=keywords,
            found=False,
            reason="no keyword match found in section text",
        )

    windows = _merge_windows(
        [
            (
                max(0, m.start() - context_before),
                min(len(text), m.end() + context_after),
            )
            for m in matches
        ]
    )
    excerpt = "\n\n[...]\n\n".join(text[start:end].strip() for start, end in windows)

    return KeywordAnchoredText(
        keywords=keywords,
        found=True,
        text=excerpt,
        match_count=len(matches),
    )


def _merge_windows(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    windows.sort()
    merged = [windows[0]]
    for start, end in windows[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + MERGE_GAP:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
