# Interactive tour of the pipeline, one ticker, one stage at a time.
#
# Run from backend/: python scripts/walkthrough.py AAPL
# Add --llm to also run the LLM extraction (real Claude API calls - needs
# ANTHROPIC_API_KEY and SEC_USER_AGENT). Without it, the walkthrough stops
# after the parser stage (no API key needed, no cost).
#
# Each stage prints what that stage produced, then waits for Enter so you
# can read it before moving on. Pass --no-pause to run straight through.

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.edgar.client import Client
from app.edgar.resolve import resolve_filing_pair
from app.parser.items import extract_items
from app.xbrl.extract import extract_all

RUN_LLM = "--llm" in sys.argv
PAUSE = "--no-pause" not in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ticker = args[0] if args else "AAPL"


def stage(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    if PAUSE:
        input("(Enter to continue) ")


# ---------------------------------------------------------------------
stage("LAYER 0 - filing resolution (app/edgar/resolve.py)")

current, prior = resolve_filing_pair(ticker)
print(f"ticker:          {current.ticker}")
print(f"cik:             {current.cik}")
print(f"accession:       {current.accession}")
print(f"filing_date:     {current.filing_date}")
print(f"fiscal_year_end: {current.fiscal_year_end}")
print(f"cached_path:     {current.cached_path}")
print(f"prior_accession: {current.prior_accession}")
print(f"\nprior filing:    {prior.accession if prior else '(none - first 10-K)'}")

# ---------------------------------------------------------------------
stage("LAYER 1 - XBRL metrics (app/xbrl/extract.py)")

client = Client()
snapshots = extract_all(client, current)
print(f"{len(snapshots)} MetricSnapshots extracted:\n")
for s in snapshots:
    print(
        f"  {s.metric_key:<24} {s.value:>18,.2f} {s.unit:<8} "
        f"(tag: {s.xbrl_tag}, source: {s.source})"
    )

# ---------------------------------------------------------------------
stage("LAYER 2a - Item-section parsing (app/parser/items.py)")

filing_html = Path(current.cached_path).read_text(encoding="utf-8")
items = extract_items(filing_html, ["1", "1A", "7", "8", "9A"])
for key, section in items.items():
    if section.found:
        preview = section.text[:200].replace("\n", " ")
        print(f"  Item {key:<3} FOUND   {len(section.text):>7,} chars   {preview}...")
        if section.reason:
            print(f"              note: {section.reason}")
    else:
        print(f"  Item {key:<3} NOT FOUND   {section.reason}")

if not RUN_LLM:
    print("\n(stopping here - pass --llm to also run the Claude extraction)")
    sys.exit(0)

# ---------------------------------------------------------------------
stage("LAYER 2b - qualitative LLM extraction (app/extraction/pipeline.py)")
print("Making real Claude API calls - this costs money and takes a bit.\n")

from app.extraction.pipeline import extract_qualitative

result = extract_qualitative(current, prior)
print(result.model_dump_json(indent=2))
