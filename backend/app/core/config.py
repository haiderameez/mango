from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/mango"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30

    # Notifications. Unset topic ARN -> notifications are logged instead of published.
    aws_sns_topic_arn: str | None = None
    aws_region: str = "us-east-1"

    log_level: str = "INFO"

    # Provider is explicit and model identifiers stay pinned, never aliases.
    llm_provider: Literal["gemini", "anthropic", "openrouter"] = "gemini"

    google_api_key: str | None = None
    # Pinned deliberately, not an alias: "gemini-flash-latest" moved to gemini-3.8-flash,
    # whose free tier allows 20 requests a day rather than the 250 this once assumed. A
    # budget guard cannot protect a limit it was not told about, so the limits below must
    # match whatever model this names - the quota is per model.
    gemini_model: str = "gemini-3.5-flash"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    openrouter_api_key: str | None = None
    # Pinned non-thinking model: strong structured SRE analysis at a fraction of GPT-4.1
    # Mini's current listed token price, without extra reasoning tokens.
    openrouter_model: str = "qwen/qwen3-30b-a3b-instruct-2507"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    incident_history_similarity_floor: float = 0.75
    incident_history_limit: int = 3
    incident_history_enabled: bool = True

    # Provider budget. Defaults are the conservative end of Gemini's free tier; check your
    # own limits in Google AI Studio and raise them here. Mango never sends a request that
    # would exceed these, it queues or defers instead.
    llm_requests_per_minute: int = 10
    # 20 is the measured free-tier allowance for a current flash model. Raise it to your
    # own figure from https://aistudio.google.com/rate-limit.
    llm_requests_per_day: int = 20
    llm_max_retries: int = 5
    # Fallback backoff when the provider rate-limits us without saying for how long.
    llm_cooldown_seconds: int = 60
    # Log each agent's reasoning as it runs, and store a summary with its execution.
    llm_show_thinking: bool = True
    llm_thinking_max_chars: int = 4000
    llm_quota_timezone: str = "America/Los_Angeles"
    redis_url: str = "redis://localhost:6379/0"
    investigation_worker_concurrency: int = 4
    otel_endpoint: str | None = None
    slack_webhook_url: str | None = None

    # A PENDING or RUNNING investigation older than this is treated as abandoned (the
    # process died mid-run) and no longer blocks a retry.
    stale_run_minutes: int = 60

    # Evidence source: JSONL log file written by DummyCommerce.
    dummycommerce_log_path: str = "../dummycommerce/logs/app.jsonl"
    evidence_max_records: int = 50
    evidence_window_minutes: int = 15

    @field_validator("jwt_secret_key")
    @classmethod
    def _refuse_the_placeholder(cls, value: str) -> str:
        """The example file ships a placeholder; deploying it would make every token forgeable."""
        if value.strip() in {"", "change-me"}:
            raise ValueError(
                "JWT_SECRET_KEY is unset or still the placeholder. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
