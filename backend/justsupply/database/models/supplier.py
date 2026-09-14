from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from justsupply.database.base import Base


class SupplierModel(Base):
    __tablename__ = "suppliers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    website: Mapped[str | None] = mapped_column(String(2083), nullable=True)
    commodities: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
