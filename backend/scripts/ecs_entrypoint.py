"""Configure AWS-provided connection secrets and start one Mango container role."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy.engine import URL


def configure_environment() -> None:
    """Build connection URLs inside the container so secrets stay out of task definitions."""
    if os.environ.get("DATABASE_HOST"):
        os.environ["DATABASE_URL"] = URL.create(
            "postgresql+psycopg",
            username=os.environ["DATABASE_USER"],
            password=os.environ["DATABASE_PASSWORD"],
            host=os.environ["DATABASE_HOST"],
            port=int(os.environ.get("DATABASE_PORT", "5432")),
            database=os.environ.get("DATABASE_NAME", "mango"),
        ).render_as_string(hide_password=False)

    if os.environ.get("REDIS_HOST"):
        os.environ["REDIS_URL"] = URL.create(
            "rediss" if os.environ.get("REDIS_TLS", "false").lower() == "true" else "redis",
            host=os.environ["REDIS_HOST"],
            port=int(os.environ.get("REDIS_PORT", "6379")),
            database="0",
        ).render_as_string(hide_password=False)

    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    api_key = os.environ.get("LLM_API_KEY")
    key_name = {
        "gemini": "GOOGLE_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }.get(provider)
    if api_key and key_name:
        os.environ[key_name] = api_key


def main(role: str) -> None:
    configure_environment()
    if role == "api":
        import subprocess

        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        os.execvp(
            "uvicorn",
            [
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                os.environ.get("PORT", "8000"),
            ],
        )

    concurrency_name = (
        "INGEST_WORKER_CONCURRENCY"
        if role == "ingest-worker"
        else "INVESTIGATION_WORKER_CONCURRENCY"
    )
    if role in {"worker", "ingest-worker"}:
        queue = "ingestion" if role == "ingest-worker" else "investigations"
        os.execvp(
            "celery",
            [
                "celery",
                "-A",
                "app.celery_app:celery_app",
                "worker",
                "--loglevel=INFO",
                f"--concurrency={os.environ.get(concurrency_name, '4')}",
                "-Q",
                queue,
            ],
        )
    if role == "scheduler":
        os.execvp(
            "celery",
            ["celery", "-A", "app.celery_app:celery_app", "beat", "--loglevel=INFO"],
        )
    raise SystemExit(f"Unknown Mango ECS role: {role}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts/ecs_entrypoint.py api|worker|ingest-worker|scheduler"
        )
    # Keep direct script execution independent of the current working directory.
    os.chdir(Path(__file__).resolve().parents[1])
    main(sys.argv[1])
