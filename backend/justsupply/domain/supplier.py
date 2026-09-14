from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, HttpUrl


class Commodity(StrEnum):
    COCOA = "cocoa"
    COFFEE = "coffee"


class Supplier(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    legal_name: str
    country_code: str
    website: HttpUrl | None
    commodities: tuple[Commodity, ...]
    created_at: datetime
    updated_at: datetime
