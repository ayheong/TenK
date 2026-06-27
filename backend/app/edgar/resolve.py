from app.edgar.models import FilingRecord


def resolve_filing(ticker: str) -> FilingRecord:
    """Ticker → latest 10-K metadata + cached HTML under data/cache/."""
    raise NotImplementedError
