from uuid import UUID

from celery import Task  # type: ignore[import-untyped]

from justsupply.core.config import get_settings
from justsupply.database.session import SessionFactory
from justsupply.dependencies import build_document_ingestion_processor
from justsupply.integrations.ai import AiExtractionError
from justsupply.services.rag import RagProviderError
from justsupply.worker import celery_app

settings = get_settings()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=Task,
    name="justsupply.process_document_ingestion",
    max_retries=settings.celery_task_max_retries,
)
def process_document_ingestion(self: Task, job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    with SessionFactory() as session:
        processor = build_document_ingestion_processor(session)
        try:
            processor.process(parsed_job_id)
        except (AiExtractionError, RagProviderError) as error:
            if self.request.retries >= settings.celery_task_max_retries:
                processor.fail(parsed_job_id, error)
                raise
            processor.defer(parsed_job_id, error)
            countdown = settings.celery_task_retry_delay_seconds * (2**self.request.retries)
            raise self.retry(exc=error, countdown=countdown) from error
        except Exception as error:
            processor.fail(parsed_job_id, error)
            raise
