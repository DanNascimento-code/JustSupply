from celery import Celery  # type: ignore[import-untyped]

from justsupply.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "justsupply",
    broker=settings.celery_broker_url,
    include=["justsupply.tasks.document_ingestion"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_ignore_result=True,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
)
