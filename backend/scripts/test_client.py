# Manual test for app.edgar.resolve
# Run from backend/: python scripts/test_client.py

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.resolve import resolve_filing

record = resolve_filing("AAPL")
print(record)