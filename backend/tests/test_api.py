from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api import main, service
from app.api.models import Analysis
from app.edgar.models import FilingRecord
from app.extraction.llm import ExtractionError
from app.xbrl.models import MetricSnapshot
from tests.test_qualitative_scoring import _extraction

client = TestClient(main.app)


def _filing() -> FilingRecord:
    return FilingRecord(
        ticker="TEST",
        cik=1,
        accession="0000000000-26-000001",
        filing_date="2026-02-15",
        fiscal_year_end="2025-12-31",
        html_url="https://example.com/10k.htm",
        cached_path="/tmp/10k.htm",
        prior_accession="0000000000-25-000001",
    )


def _metric(key: str, value: float) -> MetricSnapshot:
    return MetricSnapshot(
        ticker="TEST",
        cik=1,
        fiscal_year=2025,
        metric_key=key,
        value=value,
        unit="ratio",
        xbrl_tag=key,
        source="company_facts",
        filed_at=date(2026, 2, 15),
    )


@pytest.fixture
def stub_pipeline(monkeypatch):
    seen: dict = {}

    def fake_extract_qualitative(filing, prior, *, llm):
        seen["llm"] = llm
        return _extraction()

    monkeypatch.setattr(service, "resolve_filing_pair", lambda t: (_filing(), None))
    monkeypatch.setattr(
        service,
        "extract_all",
        lambda c, f: [
            _metric("working_capital_ratio", 1.5),
            _metric("debt_to_equity", 1.0),
        ],
    )
    monkeypatch.setattr(service, "extract_qualitative", fake_extract_qualitative)
    monkeypatch.setattr(service, "Client", lambda: None)
    return seen


def test_analyze_returns_all_five_subscores_in_order(stub_pipeline) -> None:
    analysis = service.analyze("TEST", use_llm=False)

    assert [s.key for s in analysis.subscores] == [
        "liquidity",
        "leverage",
        "litigation_regulatory",
        "governance",
        "disclosure_change",
    ]
    assert analysis.subscores[0].available
    assert analysis.filing.ticker == "TEST"
    assert "cached_path" not in analysis.filing.model_dump()
    assert {m.key for m in analysis.metrics} == {
        "working_capital_ratio",
        "debt_to_equity",
    }


def test_llm_is_disabled_unless_requested(stub_pipeline) -> None:
    service.analyze("TEST", use_llm=False)

    assert isinstance(stub_pipeline["llm"], service.DisabledLLM)
    with pytest.raises(ExtractionError, match="LLM disabled"):
        stub_pipeline["llm"].extract(system="", text="", schema=object)


def test_llm_flag_uses_real_client(stub_pipeline, monkeypatch) -> None:
    monkeypatch.setattr(service, "LLMClient", lambda: "real-client")

    service.analyze("TEST", use_llm=True)

    assert stub_pipeline["llm"] == "real-client"


def test_endpoint_serializes_analysis(stub_pipeline) -> None:
    response = client.get("/api/analyze/TEST")

    assert response.status_code == 200
    body = Analysis.model_validate(response.json())
    assert body.llm_enabled is False


def test_unknown_ticker_is_404(monkeypatch) -> None:
    def raise_unknown(ticker: str, *, use_llm: bool):
        raise ValueError(f"Ticker not found: {ticker}")

    monkeypatch.setattr(service, "analyze", raise_unknown)

    response = client.get("/api/analyze/ZZZZ")

    assert response.status_code == 404
    assert "Ticker not found" in response.json()["detail"]


def test_invalid_ticker_is_rejected() -> None:
    assert client.get("/api/analyze/../etc").status_code in {404, 422}
    assert client.get("/api/analyze/12345").status_code == 422


def test_llm_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.get("/api/analyze/TEST?llm=true")

    assert response.status_code == 400
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_health_reports_llm_availability(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert client.get("/api/health").json() == {"llm_available": True}

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert client.get("/api/health").json() == {"llm_available": False}
