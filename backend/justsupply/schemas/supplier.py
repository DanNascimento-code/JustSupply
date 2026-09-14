from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

from justsupply.domain.supplier import Commodity

SupplierName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
]
CountryCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$"),
]


class SupplierWrite(BaseModel):
    legal_name: SupplierName
    country_code: CountryCode
    website: HttpUrl | None = None
    commodities: list[Commodity] = Field(min_length=1)

    @field_validator("country_code")
    @classmethod
    def uppercase_country_code(cls, country_code: str) -> str:
        return country_code.upper()

    @field_validator("commodities")
    @classmethod
    def remove_duplicate_commodities(cls, commodities: list[Commodity]) -> list[Commodity]:
        return list(dict.fromkeys(commodities))


class SupplierCreate(SupplierWrite):
    pass


class SupplierUpdate(SupplierWrite):
    pass


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    country_code: str
    website: HttpUrl | None
    commodities: list[Commodity]
    created_at: datetime
    updated_at: datetime


class SupplierListResponse(BaseModel):
    items: list[SupplierRead]
    total: int
