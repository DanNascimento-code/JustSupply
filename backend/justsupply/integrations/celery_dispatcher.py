from uuid import UUID

from kombu.exceptions import OperationalError  # type: ignore[import-untyped]

from justsupply.services.document_ingestion import DocumentJobDispatchError
from justsupply.worker import celery_app

DOCUMENT_INGESTION_TASK = "justsupply.process_document_ingestion"


class CeleryDocumentJobDispatcher:
    def enqueue(self, job_id: UUID) -> None:
        try:
            celery_app.send_task(
                DOCUMENT_INGESTION_TASK,
                args=[str(job_id)],
                task_id=str(job_id),
            )
        except OperationalError as error:
            raise DocumentJobDispatchError("The background worker queue is unavailable.") from error
