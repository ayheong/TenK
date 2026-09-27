# Changelog

All notable changes to TenK are recorded here, newest first.

## Unreleased

- Added `app/extraction`: Layer 2 qualitative extraction. `extract_qualitative`
  takes a resolved filing (and optionally its prior year) and returns a
  `QualitativeExtraction` bundling five schema-constrained Claude calls —
  risk-factor changes vs prior year (Item 1A), management tone / forward
  guidance (Item 7), going-concern & material-weakness (Item 8 / 9A),
  related-party transactions (Item 8 notes), and revenue concentration
  (Item 1 / Item 7). Each result carries provenance: a section the parser
  can't locate is recorded `found=False` with no API call; a section found
  but whose call fails or is refused is `found=True` with `error` set, so
  one bad section never sinks the filing. Large sections are keyword-anchored
  (reusing `anchors.py`) before being sent, and the related-party / revenue-
  concentration extractors skip the API entirely and return a structured
  negative when no relevant keyword appears. Output schemas
  (`app/extraction/models.py`) use booleans and enums close to what Layer 2.5
  risk scoring will consume. Model defaults to `claude-opus-5`, overridable
  via `TENK_EXTRACTION_MODEL`. Uses the Anthropic SDK's `messages.parse`
  (structured outputs) with adaptive thinking. 10 tests, all with a fake LLM
  — no network in CI.
- Added `resolve_filing_pair`: resolves the latest 10-K plus the prior
  year's, both with cached HTML, for year-over-year qualitative diffs.
  `resolve_filing` refactored onto a shared `_build_filing_record` helper
  (behavior unchanged).
- Added `anthropic>=1.2` as a dependency.

- Fixed `extract_items`: some filers (NVIDIA, JPMorgan, Chevron) satisfy
  Item 8 with a short cross-reference notice instead of placing the
  financial statements at that heading — the real statements sit
  elsewhere in the document, sometimes inside a later Item, sometimes in
  an unlabeled block with no Item number of its own. Previously this
  returned `found=True` with the ~200-char notice itself, silently
  passing off a redirect as real content. Now searches forward from Item
  8 for the actual "Report of Independent Registered Public Accounting
  Firm" heading, distinguishing it from the (also present) index entry by
  what follows: a bare page number for the index, real prose for the
  report. Verified across a 12-filer test collection spanning tech,
  banking, energy, pharma, and retail (AAPL/MSFT/TSLA/NVDA/GOOG/AMZN/JPM/
  JNJ/KO/WMT/CVX/PLTR) — all 12 now return real Item 8 content, 3 via the
  redirect path. Item 7 (MD&A) has the same cross-reference problem for
  JPM/CVX but no reliable equivalent anchor (its title phrase is reused
  in narrative cross-references elsewhere, unlike the audit report
  heading) — left as an honest short stub rather than guessed at.

- Added `app/parser/anchors.py`: `extract_keyword_anchored_text` pulls just
  the text around keyword matches out of a large section (e.g. the
  related-party-transactions footnote inside Item 8's full financial
  statements), instead of sending the whole section to an LLM. Merges
  nearby matches into one excerpt; reports `found=False` honestly when no
  keyword appears at all, rather than an empty match. Verified against
  real Item 8 sections: 96–98% size reduction on TSLA/MSFT; correctly
  reports "not found" for AAPL (no related-party disclosure) and NVDA
  (financials live outside this section) rather than guessing.

- Added `app/parser`: `extract_items` splits cached 10-K HTML into raw text
  per Item number (1, 1A, 7, 8, 9A), needed before qualitative sections can
  be extracted with an LLM. Skips the table of contents (detected as a
  tight cluster of heading matches near the top) and, critically, anchors
  heading matches to the start of an HTML block so a cross-reference
  mid-sentence (e.g. "...appearing under Item 9A." inside an auditor's
  report) isn't mistaken for a real heading — an earlier version of this
  without the anchor silently truncated TSLA's Item 8 from ~172K chars to
  ~2.7K. Items it can't confidently locate are reported as not-found with
  a reason rather than guessed at. 20/20 target sections found across
  AAPL/TSLA/NVDA/MSFT.

- Added `current_assets`/`current_liabilities` as canonical metrics and
  `working_capital_ratio` as a derived ratio, completing the four derived
  metrics named in CONTEXT.md's spec. Verified against AAPL/TSLA/NVDA —
  values are directionally sane (AAPL <1, consistent with it running lean
  on working capital; TSLA/NVDA >1, consistent with larger cash cushions).
- Added derived ratios computed from already-extracted metrics, no extra
  fetch: `gross_margin`, `rd_pct_revenue`, and `net_income_yoy_pct` (the
  latter reads the prior-year comparative figure already present in the
  same Company Facts payload). `extract_all` fetches Company Facts once
  and returns canonical + derived metrics together. `working_capital_ratio`
  is not yet derivable — current assets/liabilities aren't extracted.
- Added `app/xbrl`: `extract_metrics` pulls canonical `MetricSnapshot`s
  (revenue, net income, operating cash flow, long/short-term debt, gross
  profit, shares outstanding, R&D expense) from the Company Facts API for a
  resolved filing, with a fallback tag list per metric since filers use
  different XBRL tags for the same concept (verified against real AAPL and
  TSLA filings — TSLA uses different debt tags than AAPL).
- Added a token-bucket rate limiter (~10 req/sec) and exponential backoff on
  429/503 to the EDGAR HTTP client.
- `find_10k_filings` now reads `primaryDocument`/`reportDate` straight from
  the SEC submissions API instead of fetching and parsing a filing's
  directory index — one fewer request per filing, no guessing which `.htm`
  is primary.
- `resolve_filing` downloads and caches the primary 10-K HTML under
  `data/cache/`, skipping the request when the accession is already cached,
  and now also resolves the prior-year 10-K accession for YoY comparisons.
- Added `find_latest_10k` to resolve the most recent 10-K accession and
  filing date from SEC submissions, with unit tests and cached fixtures.
