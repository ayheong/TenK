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

import httpx
from os import getenv

SEC_USER_AGENT = getenv("SEC_USER_AGENT")

HEADERS = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

class Client:
    def get_json(self, url: str) -> dict:
        with httpx.Client(headers=HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

