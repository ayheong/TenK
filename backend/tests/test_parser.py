from app.parser.items import extract_items

BUSINESS_BODY = "Lorem ipsum business description. " * 20
RISK_BODY = "Lorem ipsum risk factor description. " * 20
MDA_BODY_1 = "Lorem ipsum discussion of results of operations and revenue trends. " * 15
MDA_BODY_2 = (
    "As discussed under Item 9A. below, our disclosure controls were "
    "effective. " + "More MD&A analysis follows about market conditions. " * 15
)
FINANCIALS_BODY = "Lorem ipsum consolidated financial statement notes. " * 20
CONTROLS_BODY = "Lorem ipsum controls and procedures evaluation. " * 20

FILING_HTML = f"""
<html><body>
<div><p>TABLE OF CONTENTS</p></div>
<table>
<tr><td>Item 1.</td><td>Business</td><td>1</td></tr>
<tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>
<tr><td>Item 6.</td><td>[Reserved]</td><td>19</td></tr>
<tr><td>Item 7.</td><td>MD&amp;A</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements</td><td>28</td></tr>
<tr><td>Item 9A.</td><td>Controls and Procedures</td><td>52</td></tr>
</table>
<div><p>PART I</p></div>
<div><p>{"This Annual Report on Form 10-K contains forward-looking " * 15}</p></div>
<div><p>Item 1. Business</p><p>{BUSINESS_BODY}</p></div>
<div><p>Item 1A. Risk Factors</p><p>{RISK_BODY}</p></div>
<div><p>Item 6. [Reserved]</p></div>
<div><p>Item 7. Management's Discussion and Analysis</p>
<p>{MDA_BODY_1}</p><p>{MDA_BODY_2}</p></div>
<div><p>Item 8. Financial Statements and Supplementary Data</p>
<p>{FINANCIALS_BODY}</p></div>
<div><p>Item 9A. Controls and Procedures</p><p>{CONTROLS_BODY}</p></div>
</body></html>
"""


def test_extract_items_skips_table_of_contents() -> None:
    results = extract_items(FILING_HTML, ["1"])

    assert results["1"].found
    # Must start at the real heading, not the ToC row (which would include
    # "Business1" glued to the page number with no real content after it).
    assert results["1"].text.startswith("Item 1. Business")
    assert "Lorem ipsum business" in results["1"].text


def test_extract_items_ignores_cross_reference_mid_paragraph() -> None:
    results = extract_items(FILING_HTML, ["7", "9A"])

    mda = results["7"]
    assert mda.found
    # The mid-sentence "Item 9A." cross-reference inside Item 7's own text
    # must not truncate the section early.
    assert "More MD&A analysis follows" in mda.text
    assert "controls and procedures evaluation" not in mda.text

    controls = results["9A"]
    assert controls.found
    assert controls.text.startswith("Item 9A. Controls and Procedures")


def test_extract_items_handles_adjacent_real_headings() -> None:
    # Item 6 has almost no content ("[Reserved]") and sits directly before
    # Item 7 with only a small real gap between them — must not be
    # re-absorbed into the "still in the table of contents" case.
    results = extract_items(FILING_HTML, ["7"])

    assert results["7"].found
    assert results["7"].text.startswith("Item 7.")


def test_extract_items_reports_missing_item_honestly() -> None:
    results = extract_items(FILING_HTML, ["2"])

    assert results["2"].found is False
    assert results["2"].text is None
    assert "no confident heading match" in results["2"].reason


def test_extract_items_returns_entry_for_every_requested_item() -> None:
    results = extract_items(FILING_HTML, ["1", "1A", "7", "8", "9A"])

    assert set(results.keys()) == {"1", "1A", "7", "8", "9A"}
    assert all(r.found for r in results.values())
