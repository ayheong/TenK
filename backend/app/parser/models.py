from pydantic import BaseModel


class ItemSection(BaseModel):
    item_number: str
    found: bool
    text: str | None = None
    reason: str | None = None
