"""Demo API and static front end. Run from `backend/`:

uvicorn app.api.main:app --reload
"""

import os
import re

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.api import REPO_ROOT, service
from app.api.models import Analysis

FRONTEND_DIR = REPO_ROOT / "frontend"
TICKER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,9}$")

app = FastAPI(title="TenK demo")


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"llm_available": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.get("/api/analyze/{ticker}", response_model=Analysis)
def analyze(ticker: str, llm: bool = False) -> Analysis:
    if not TICKER_PATTERN.match(ticker):
        raise HTTPException(status_code=422, detail=f"Invalid ticker: {ticker}")
    if llm and not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=400, detail="ANTHROPIC_API_KEY is not set")
    try:
        return service.analyze(ticker, use_llm=llm)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"SEC request failed: {exc}"
        ) from exc


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
