# SEC EDGAR HTTP client
#
#   https://www.sec.gov/files/company_tickers.json
#     — ticker → CIK lookup
#   https://data.sec.gov/submissions/CIK##########.json
#     — filing history; find latest 10-K accession
#   https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{accession}-index.json
#     — list files in a filing; pick primary .htm
#   https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}.htm
#     — download 10-K HTML document
#   https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json
#     — all XBRL financial metrics for a company
#   https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/{tag}.json
#     — single metric fallback when facts API lacks a tag

import time
from os import getenv

import httpx

SEC_USER_AGENT = getenv("SEC_USER_AGENT")

HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

RETRYABLE_STATUS_CODES = {429, 503}


class TokenBucket:
    """Caps calls to `rate` per second, allowing bursts up to `capacity`."""

    def __init__(
        self,
        rate: float = 10.0,
        capacity: float | None = None,
        time_func=time.monotonic,
        sleep_func=time.sleep,
    ) -> None:
        self.rate = rate
        self.capacity = capacity if capacity is not None else rate
        self.tokens = self.capacity
        self._time = time_func
        self._sleep = sleep_func
        self._last_refill = self._time()

    def acquire(self) -> None:
        self._refill()
        if self.tokens < 1:
            self._sleep((1 - self.tokens) / self.rate)
            self._refill()
        self.tokens -= 1

    def _refill(self) -> None:
        now = self._time()
        elapsed = now - self._last_refill
        self._last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)


class Client:
    """Rate-limited GET with exponential backoff on 429/503."""

    def __init__(
        self,
        rate_limiter: TokenBucket | None = None,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        sleep_func=time.sleep,
    ) -> None:
        self.rate_limiter = rate_limiter or TokenBucket(rate=10.0)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep_func

    def get_json(self, url: str) -> dict:
        return self._get(url).json()

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def _get(self, url: str) -> httpx.Response:
        attempt = 0
        while True:
            self.rate_limiter.acquire()
            with httpx.Client(headers=HEADERS) as client:
                response = client.get(url)

            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response

            attempt += 1
            if attempt > self.max_retries:
                response.raise_for_status()

            self._sleep(self.backoff_base * (2 ** (attempt - 1)))
