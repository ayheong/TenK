# TenK

An application that analyzes SEC 10-K filings from EDGAR, extracts financial signals, and generates investor friendly reports.

## Demo

Run the pipeline for a ticker and review each stage in the browser.

```bash
cd backend
python -m uvicorn app.api.main:app --reload
```

Then open http://localhost:8000.
Set `SEC_USER_AGENT` in `.env` first.
The Claude extraction is off by default and needs `ANTHROPIC_API_KEY`.
