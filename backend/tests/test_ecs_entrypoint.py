import os

from scripts.ecs_entrypoint import configure_environment


def test_builds_database_url_with_escaped_password(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://old")
    monkeypatch.setenv("DATABASE_HOST", "db.internal")
    monkeypatch.setenv("DATABASE_USER", "mango")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss:/word")
    monkeypatch.setenv("DATABASE_NAME", "mango")

    configure_environment()

    assert (
        os.environ["DATABASE_URL"]
        == "postgresql+psycopg://mango:p%40ss%3A%2Fword@db.internal:5432/mango"
    )


def test_builds_redis_url_from_managed_endpoint(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://old")
    monkeypatch.setenv("REDIS_HOST", "cache.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_TLS", "true")

    configure_environment()

    assert os.environ["REDIS_URL"] == "rediss://cache.internal:6380/0"


def test_maps_provider_secret_to_selected_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_API_KEY", "secret-value")
    monkeypatch.setenv("OPENROUTER_API_KEY", "old-key")

    configure_environment()

    assert os.environ["OPENROUTER_API_KEY"] == "secret-value"


def test_leaves_provider_keys_alone_when_no_key_is_configured(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    configure_environment()

    assert os.getenv("GOOGLE_API_KEY") is None
