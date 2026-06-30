# Manual test for app.edgar.client
# Run from backend/: python scripts/test_client.py

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.client import Client
from app.edgar.resolve import lookup_cik

client = Client()
cik = lookup_cik(client, "AAPL")
print(cik)