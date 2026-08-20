from app.parser.anchors import extract_keyword_anchored_text

RELATED_PARTY_KEYWORDS = ["related part"]


def test_extracts_window_around_a_single_match() -> None:
    text = (
        "Lorem ipsum unrelated financial statement content. " * 300
        + "Related Party Transactions. The Company leases office space "
        "from an entity controlled by its CEO for $2 million annually."
        + " More unrelated content follows here and continues on. " * 300
    )

    result = extract_keyword_anchored_text(text, RELATED_PARTY_KEYWORDS)

    assert result.found
    assert result.match_count == 1
    assert "Related Party Transactions" in result.text
    assert "leases office space" in result.text
    # Excerpt should be much smaller than the full document.
    assert len(result.text) < len(text) / 2


def test_merges_nearby_matches_into_one_excerpt() -> None:
    text = (
        "Related party A. " + "filler " * 10 + "Also a related party B deal."
    )

    result = extract_keyword_anchored_text(
        text, RELATED_PARTY_KEYWORDS, context_before=10, context_after=10
    )

    assert result.found
    assert result.match_count == 2
    # Merged into a single contiguous excerpt, not two separate chunks.
    assert result.text.count("[...]") == 0


def test_keeps_far_apart_matches_as_separate_excerpts() -> None:
    text = (
        "Related party A mention here."
        + " padding " * 500
        + "Related party B mention here."
    )

    result = extract_keyword_anchored_text(
        text, RELATED_PARTY_KEYWORDS, context_before=20, context_after=20
    )

    assert result.found
    assert result.match_count == 2
    assert "[...]" in result.text


def test_reports_not_found_honestly_when_no_keyword_present() -> None:
    text = "The information required by this Item is set forth elsewhere."

    result = extract_keyword_anchored_text(text, RELATED_PARTY_KEYWORDS)

    assert result.found is False
    assert result.text is None
    assert result.match_count == 0
    assert "no keyword match" in result.reason


def test_case_insensitive_matching() -> None:
    text = "Lorem ipsum. RELATED PARTY disclosures follow. " + "x" * 50

    result = extract_keyword_anchored_text(text, RELATED_PARTY_KEYWORDS)

    assert result.found
    assert result.match_count == 1
