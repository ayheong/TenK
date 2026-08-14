import pytest


@pytest.fixture(autouse=True)
def sec_user_agent() -> None:
    """Tests mock HTTP; set a dummy User-Agent so Client can initialize."""
    import app.edgar.client as client_module

    agent = "TenKAnalyzer test@example.com"
    client_module.SEC_USER_AGENT = agent
    client_module.HEADERS = {
        "User-Agent": agent,
        "Accept": "application/json",
    }
