from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from justsupply.database.base import Base


class BrandModel(Base):
    __tablename__ = "brands"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    barcode: Mapped[str] = mapped_column(String(14), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    brand_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", ondelete="SET NULL"),
        nullable=True,
    )
    image_url: Mapped[str | None] = mapped_column(String(2083), nullable=True)
    catalog_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceSourceModel(Base):
    __tablename__ = "evidence_sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(2083), nullable=False)
    url_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ClaimModel(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "(subject_scope = 'product' AND product_id IS NOT NULL AND brand_id IS NULL) "
            "OR (subject_scope = 'brand' AND brand_id IS NOT NULL AND product_id IS NULL)",
            name="ck_claims_exactly_one_subject",
        ),
        CheckConstraint(
            "status IN ('supported', 'mixed', 'concern', 'not_disclosed', 'unknown')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "origin IN ('catalog', 'ai_research')",
            name="ck_claims_origin",
        ),
        Index(
            "uq_claims_product_dimension",
            "product_id",
            "dimension",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "uq_claims_brand_dimension",
            "brand_id",
            "dimension",
            unique=True,
            postgresql_where=text("brand_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    subject_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
    )
    brand_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("brands.id", ondelete="CASCADE"),
        nullable=True,
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    localized_content: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiResearchRunModel(Base):
    __tablename__ = "ai_research_runs"
    __table_args__ = (Index("ix_ai_research_runs_product_id", "product_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_response_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceRecordModel(Base):
    __tablename__ = "evidence_records"
    __table_args__ = (
        Index(
            "uq_evidence_records_source_fingerprint",
            "source_id",
            "fingerprint",
            unique=True,
        ),
        Index("ix_evidence_records_research_run_id", "research_run_id"),
        Index(
            "ix_evidence_records_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    research_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_research_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR(1536), nullable=True)


class ClaimEvidenceRecordModel(Base):
    __tablename__ = "claim_evidence_records"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_claim_evidence_records_relationship",
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("evidence_records.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
