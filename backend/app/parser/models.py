from pydantic import BaseModel


class ItemSection(BaseModel):
    item_number: str
    found: bool
    text: str | None = None
    reason: str | None = None


class KeywordAnchoredText(BaseModel):
    keywords: list[str]
    found: bool
    text: str | None = None
    match_count: int = 0
    reason: str | None = None
