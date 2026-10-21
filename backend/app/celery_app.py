from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.observability import configure_celery_tracing

celery_app = Celery(
    "mango",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    broker_transport_options={"visibility_timeout": 18_000},
    result_expires=3600,
    task_routes={"app.tasks.run_investigation": {"queue": "investigations"}},
)

worker_process_init.connect(lambda **_kwargs: configure_celery_tracing(), weak=False)
