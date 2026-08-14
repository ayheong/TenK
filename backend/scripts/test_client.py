# Manual test for app.edgar.client
# Run from backend/: python scripts/test_client.py

from dotenv import load_dotenv
import json
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.client import Client
from app.edgar.resolve import submissions_url, find_latest_10k, lookup_cik

client = Client()
cik = lookup_cik(client, "AAPL")
accession, filing_date = find_latest_10k(client, cik)
acc = accession.replace("-", "")
url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
index = client.get_json(url)
path = Path("tests/fixtures/filing_index.json")
path.write_text(json.dumps(index, indent=2))