# Changelog

All notable changes to TenK are recorded here, newest first.

## Unreleased

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
