from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from justsupply.database.models import (
    BrandModel,
    DocumentChunkModel,
    SourceDocumentModel,
)
from justsupply.domain.rag import IndexedChunk, RetrievedChunk
from justsupply.repositories.brand_evidence import BrandNotFoundError


class RagDocumentNotFoundError(Exception):
    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Evidence document '{document_id}' was not found.")


class RagPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentForIndexing:
    id: UUID
    text: str


class SqlAlchemyRagRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_brand_name(self, brand_id: UUID) -> str:
        brand = self._session.get(BrandModel, brand_id)
        if brand is None:
            raise BrandNotFoundError(brand_id)
        return brand.name

    def get_document_for_indexing(self, document_id: UUID) -> DocumentForIndexing:
        document = self._session.get(SourceDocumentModel, document_id)
        if document is None:
            raise RagDocumentNotFoundError(document_id)
        return DocumentForIndexing(id=document.id, text=document.extracted_text)

    def replace_chunks(
        self,
        document_id: UUID,
        chunks: list[IndexedChunk],
        *,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> int:
        self.get_document_for_indexing(document_id)
        now = datetime.now(UTC)
        self._session.execute(
            delete(DocumentChunkModel).where(DocumentChunkModel.document_id == document_id)
        )
        self._session.add_all(
            [
                DocumentChunkModel(
                    id=uuid4(),
                    document_id=document_id,
                    chunk_index=item.chunk.index,
                    text=item.chunk.text,
                    page_number=item.chunk.page_number,
                    character_start=item.chunk.character_start,
                    character_end=item.chunk.character_end,
                    content_sha256=sha256(item.chunk.text.encode("utf-8")).hexdigest(),
                    embedding_model=embedding_model,
                    embedding_dimensions=embedding_dimensions,
                    embedding=item.embedding,
                    created_at=now,
                )
                for item in chunks
            ]
        )
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise RagPersistenceError("The document index could not be saved.") from error
        return len(chunks)

    def search(
        self,
        brand_id: UUID,
        query_embedding: list[float],
        *,
        embedding_model: str,
        embedding_dimensions: int,
        top_k: int,
    ) -> list[RetrievedChunk]:
        self.get_brand_name(brand_id)
        distance = DocumentChunkModel.embedding.cosine_distance(query_embedding).label("distance")
        rows = self._session.execute(
            select(DocumentChunkModel, SourceDocumentModel, distance)
            .join(
                SourceDocumentModel,
                SourceDocumentModel.id == DocumentChunkModel.document_id,
            )
            .where(
                SourceDocumentModel.brand_id == brand_id,
                DocumentChunkModel.embedding_model == embedding_model,
                DocumentChunkModel.embedding_dimensions == embedding_dimensions,
            )
            .order_by(distance)
            .limit(top_k)
        ).all()
        return [
            RetrievedChunk(
                id=chunk.id,
                document_id=document.id,
                text=chunk.text,
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                character_start=chunk.character_start,
                character_end=chunk.character_end,
                source_title=document.source_title,
                source_provider=document.source_provider,
                source_url=document.source_url,
                filename=document.filename,
                similarity=max(-1.0, min(1.0, 1.0 - float(row_distance))),
            )
            for chunk, document, row_distance in rows
        ]
