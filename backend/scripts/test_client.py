# Manual test for app.edgar.client
# Run from backend/: python scripts/test_client.py

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.client import Client

client = Client()
response = client.get_json("https://www.sec.gov/files/company_tickers.json")
print(len(response))