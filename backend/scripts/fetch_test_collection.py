# Fetch a small, diverse collection of 10-Ks into data/cache/ for testing
# the item parser against real-world filing structure variety (sector,
# filer agent, company size).
# Run from backend/: python scripts/fetch_test_collection.py

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.resolve import resolve_filing

TICKERS = [
    "GOOGL",  # tech / already-large Item 8 sanity check
    "AMZN",   # tech/retail
    "JPM",    # bank holding co — different statement set (no inventory etc.)
    "JNJ",    # pharma/healthcare
    "XOM",    # energy
    "WMT",    # retail
    "KO",     # consumer staples
    "PLTR",   # newer filer, smaller/different filing agent
]

if __name__ == "__main__":
    for ticker in TICKERS:
        try:
            record = resolve_filing(ticker)
            print(f"{ticker}: cached at {record.cached_path}")
        except Exception as exc:
            print(f"{ticker}: FAILED — {exc}")
