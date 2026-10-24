import ssl

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.observability import configure_celery_tracing


def redis_ssl_options(redis_url: str) -> dict[str, ssl.VerifyMode] | None:
    if redis_url.startswith("rediss://"):
        return {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    return None


celery_app = Celery(
    "mango",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks", "app.tasks_escalation"],
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
    task_routes={
        "app.tasks.run_investigation": {"queue": "investigations"},
        "app.tasks.index_resolved_incident": {"queue": "investigations"},
        "app.tasks.process_ingest_batch": {"queue": "ingestion"},
    },
    beat_schedule={
        "check-incident-escalations-every-minute": {
            "task": "app.tasks_escalation.check_due_escalations",
            "schedule": 60.0,
            "options": {"queue": "investigations"},
        }
    },
)

redis_tls = redis_ssl_options(settings.redis_url)
if redis_tls:
    celery_app.conf.update(
        broker_use_ssl=redis_tls,
        redis_backend_use_ssl=redis_tls,
    )

worker_process_init.connect(lambda **_kwargs: configure_celery_tracing(), weak=False)
