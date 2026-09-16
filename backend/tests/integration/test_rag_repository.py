import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from justsupply.database.models import BrandModel, DocumentChunkModel, SourceDocumentModel
from justsupply.database.session import SessionFactory
from justsupply.repositories.rag import SqlAlchemyRagRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_TESTS") != "1",
        reason="Set RUN_DATABASE_TESTS=1 to run PostgreSQL integration tests.",
    ),
]


def test_pgvector_retrieval_returns_the_nearest_brand_chunk() -> None:
    suffix = uuid4().hex[:12]
    brand_id = uuid4()
    document_id = uuid4()
    relevant_chunk_id = uuid4()
    other_chunk_id = uuid4()
    now = datetime.now(UTC)
    relevant_embedding = [0.0] * 1536
    relevant_embedding[0] = 1.0
    other_embedding = [0.0] * 1536
    other_embedding[1] = 1.0

    with SessionFactory() as session:
        session.add(
            BrandModel(
                id=brand_id,
                name=f"RAG brand {suffix}",
                name_key=f"rag brand {suffix}",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            SourceDocumentModel(
                id=document_id,
                brand_id=brand_id,
                filename="impact-report.txt",
                media_type="text/plain",
                byte_size=200,
                content_sha256=suffix.ljust(64, "0"),
                storage_path=f"data/uploads/{document_id}.txt",
                extracted_text="Evidence about women workers and an unrelated packaging section.",
                character_count=65,
                source_title="Impact Report",
                source_provider="Example Organization",
                source_url=f"https://example.org/rag/{suffix}",
                source_type="corporate_report",
                published_at=None,
                created_at=now,
            )
        )
        session.flush()
        session.add_all(
            [
                DocumentChunkModel(
                    id=relevant_chunk_id,
                    document_id=document_id,
                    chunk_index=0,
                    text="Women represented 48 percent of program participants.",
                    page_number=12,
                    character_start=0,
                    character_end=52,
                    content_sha256="a" * 64,
                    embedding_model="test-model",
                    embedding_dimensions=1536,
                    embedding=relevant_embedding,
                    created_at=now,
                ),
                DocumentChunkModel(
                    id=other_chunk_id,
                    document_id=document_id,
                    chunk_index=1,
                    text="The packaging section discusses recyclable paper.",
                    page_number=30,
                    character_start=0,
                    character_end=49,
                    content_sha256="b" * 64,
                    embedding_model="test-model",
                    embedding_dimensions=1536,
                    embedding=other_embedding,
                    created_at=now,
                ),
            ]
        )
        session.commit()

        results = SqlAlchemyRagRepository(session).search(
            brand_id,
            relevant_embedding,
            top_k=2,
        )

        assert results[0].id == relevant_chunk_id
        assert results[0].source_location == "page 12"
        assert results[0].similarity == pytest.approx(1.0)

        session.execute(delete(BrandModel).where(BrandModel.id == brand_id))
        session.commit()
