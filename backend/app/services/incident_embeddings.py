"""Budgeted embeddings for resolved-incident indexing and history retrieval."""
import logging

import httpx

from app.ai import quota
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError, LlmRateLimitedError
from app.observability import PROVIDER_CALLS

logger = logging.getLogger(__name__)
EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


class IncidentEmbeddingClient:
    def __init__(self, http_client=None):
        self.http_client = http_client or httpx

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured for incident history.")
        if quota.is_cooling_down():
            raise LlmRateLimitedError(
                f"The provider asked us to back off; {quota.cooldown_remaining():.0f}s left."
            )
        if not quota.has_capacity():
            raise LlmQuotaExhaustedError(
                f"The daily LLM request budget ({settings.llm_requests_per_day}) is spent. "
                f"It resets in {quota.seconds_until_reset() / 3600:.1f} hours."
            )

        quota.wait_for_rate_slot(settings.openrouter_embedding_model)
        if not quota.consume():
            raise LlmQuotaExhaustedError("The daily LLM request budget is spent.")

        try:
            response = self.http_client.post(
                EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": settings.openrouter_embedding_model,
                    "input": texts,
                    "dimensions": 768,
                },
                timeout=30,
            )
            if response.status_code == 429:
                quota.start_cooldown(settings.llm_cooldown_seconds)
                raise LlmRateLimitedError("The embedding provider rate-limited this request.")
            response.raise_for_status()
            indexed = sorted(response.json()["data"], key=lambda row: row["index"])
            embeddings = [row["embedding"] for row in indexed]
            if len(embeddings) != len(texts) or any(len(vector) != 768 for vector in embeddings):
                raise ValueError("The embedding provider returned an unexpected vector size.")
            PROVIDER_CALLS.labels("openrouter", "success").inc()
            return embeddings
        except LlmRateLimitedError:
            PROVIDER_CALLS.labels("openrouter", "error").inc()
            raise
        except Exception as error:
            PROVIDER_CALLS.labels("openrouter", "error").inc()
            logger.warning("Incident embedding request failed: %s", error.__class__.__name__)
            raise RuntimeError("Incident embedding request failed.") from error
