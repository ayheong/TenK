# Manual end-to-end test for app.extraction against a real filing.
# Makes real Claude API calls — needs ANTHROPIC_API_KEY (or an
# `ant auth login` profile) and SEC_USER_AGENT.
# Run from backend/: python scripts/test_extraction.py AAPL

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.resolve import resolve_filing_pair
from app.extraction.pipeline import extract_qualitative

ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

current, prior = resolve_filing_pair(ticker)
print(f"{ticker}: {current.accession} (prior: {prior.accession if prior else None})")

result = extract_qualitative(current, prior)
print(result.model_dump_json(indent=2))
