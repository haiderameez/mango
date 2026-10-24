from app.ai.graph import _retry_agent_error
from app.celery_app import celery_app, redis_ssl_options
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from app.services.celery_queue import INVESTIGATION_QUEUE_NAME
from app.tasks import process_ingest_batch, run_investigation


def test_celery_worker_requeues_a_task_after_worker_loss():
    assert run_investigation.acks_late is True
    assert run_investigation.reject_on_worker_lost is True


def test_graph_retries_transient_errors_but_not_quota_failures():
    assert _retry_agent_error(ConnectionError("temporary provider failure"))
    assert not _retry_agent_error(LlmQuotaExhaustedError("quota exhausted"))
    assert not _retry_agent_error(LlmRateLimitedError("provider cooldown"))


def test_celery_routes_investigations_to_the_shared_queue():
    assert (
        celery_app.conf.task_routes["app.tasks.run_investigation"]["queue"]
        == INVESTIGATION_QUEUE_NAME
    )


def test_celery_routes_ingestion_to_its_dedicated_queue():
    assert celery_app.conf.task_routes[process_ingest_batch.name]["queue"] == "ingestion"
    assert process_ingest_batch.acks_late is True
    assert process_ingest_batch.reject_on_worker_lost is True


def test_celery_enforces_certificate_validation_for_tls_redis():
    import ssl

    assert redis_ssl_options("rediss://cache.internal:6379/0") == {
        "ssl_cert_reqs": ssl.CERT_REQUIRED
    }


def test_celery_does_not_enable_tls_for_local_redis():
    assert redis_ssl_options("redis://localhost:6379/0") is None
