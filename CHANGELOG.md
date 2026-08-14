# Changelog

All notable changes to TenK are recorded here, newest first.

## Unreleased

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
