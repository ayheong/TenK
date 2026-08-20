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


AUDITOR_REPORT_BODY = (
    "To the Board of Directors and Shareholders. "
    "We have audited the accompanying consolidated balance sheets. "
    "In our opinion, the financial statements present fairly. " * 15
)

# Mirrors a real-world pattern (e.g. NVIDIA's 10-K): Item 8 is a one-line
# cross-reference instead of the actual statements, and the statements
# instead live under Item 15(a)(1), preceded by an index that lists the
# same auditor-report heading with a page number trailing on the same line.
REDIRECT_FILING_HTML = f"""
<html><body>
<div><p>TABLE OF CONTENTS</p></div>
<table>
<tr><td>Item 7.</td><td>MD&amp;A</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements</td><td>28</td></tr>
<tr><td>Item 9.</td><td>Changes in Accountants</td><td>45</td></tr>
<tr><td>Item 15.</td><td>Exhibits and Financial Statement Schedules</td><td>48</td></tr>
<tr><td>Item 16.</td><td>Form 10-K Summary</td><td>83</td></tr>
</table>
<div><p>PART I</p></div>
<div><p>{"This Annual Report on Form 10-K contains forward-looking " * 15}</p></div>
<div><p>Item 7. Management's Discussion and Analysis</p>
<p>{MDA_BODY_1}</p></div>
<div><p>Item 8. Financial Statements and Supplementary Data</p>
<p>The information required by this Item is set forth in our Consolidated
Financial Statements and Notes thereto included in this Annual Report on
Form 10-K.</p></div>
<div><p>Item 9. Changes in and Disagreements with Accountants</p>
<p>{"None. " * 20}</p></div>
<div><p>Item 15. Exhibits and Financial Statement Schedules</p>
<p>Financial Statements</p>
<p>Report of Independent Registered Public Accounting Firm (PCAOB ID: 238)</p>
<p>49</p>
<p>Consolidated Balance Sheets</p>
<p>53</p>
<div><p>Report of Independent Registered Public Accounting Firm</p>
<p>{AUDITOR_REPORT_BODY}</p></div>
</div>
<div><p>Item 16. Form 10-K Summary</p><p>Not applicable.</p></div>
</body></html>
"""


def test_extract_items_follows_item_8_redirect_to_item_15() -> None:
    results = extract_items(REDIRECT_FILING_HTML, ["8"])

    result = results["8"]
    assert result.found
    # Not the one-line cross-reference notice — the real statements.
    assert result.text.startswith("Report of Independent Registered Public Accounting Firm")
    assert "We have audited the accompanying consolidated balance sheets" in result.text
    assert "set forth in our Consolidated" not in result.text
    assert result.reason is not None
    assert "cross-reference" in result.reason


def test_extract_items_redirect_falls_back_when_no_real_heading_found() -> None:
    # Same short Item 8 stub, but no real auditor-report heading anywhere
    # to redirect to (only the index entry, which stays an index entry).
    html_no_real_heading = REDIRECT_FILING_HTML.replace(
        '<div><p>Report of Independent Registered Public Accounting Firm</p>\n'
        f"<p>{AUDITOR_REPORT_BODY}</p></div>",
        "",
    )

    result = extract_items(html_no_real_heading, ["8"])["8"]

    # Honest redirect notice, not silently dropped.
    assert result.found
    assert "set forth in our Consolidated" in result.text


# Mirrors JPMorgan's 10-K: the index entry's page number sits on its own
# following line/block rather than trailing the heading on the same line,
# and the real statements sit past Item 9 with no Item 15 boundary needed.
REDIRECT_NEXT_LINE_PAGE_NUMBER_HTML = f"""
<html><body>
<div><p>TABLE OF CONTENTS</p></div>
<table>
<tr><td>Item 7.</td><td>MD&amp;A</td><td>20</td></tr>
<tr><td>Item 8.</td><td>Financial Statements</td><td>28</td></tr>
<tr><td>Item 9.</td><td>Changes in Accountants</td><td>45</td></tr>
</table>
<div><p>PART I</p></div>
<div><p>{"This Annual Report on Form 10-K contains forward-looking " * 15}</p></div>
<div><p>Item 7. Management's Discussion and Analysis</p>
<p>{MDA_BODY_1}</p></div>
<div><p>Item 8. Financial Statements and Supplementary Data.</p>
<p>The Consolidated Financial Statements, together with the Notes thereto,
appear on pages 162-314.</p></div>
<div><p>Item 9. Changes in and Disagreements with Accountants</p>
<p>{"None. " * 20}</p></div>
<div><p>Report of Independent Registered Public Accounting Firm</p>
<p>162</p>
<p>Consolidated Balance Sheets</p></div>
<div><p>Report of Independent Registered Public Accounting Firm</p>
<p>{AUDITOR_REPORT_BODY}</p></div>
</body></html>
"""


def test_extract_items_skips_index_entry_with_page_number_on_next_line() -> None:
    result = extract_items(REDIRECT_NEXT_LINE_PAGE_NUMBER_HTML, ["8"])["8"]

    assert result.found
    assert result.text.startswith("Report of Independent Registered Public Accounting Firm")
    assert "We have audited the accompanying consolidated balance sheets" in result.text
    assert "appear on pages 162" not in result.text
