"""Application rules for indexing and retrieving resolved incident history."""
from datetime import UTC, datetime

from app.core.config import settings
from app.repositories.incident_history_repository import IncidentHistoryRepository
from app.services.incident_embeddings import IncidentEmbeddingClient


def _document(record: dict) -> str:
    fixes = record.get("fix") or []
    if isinstance(fixes, list):
        fixes = "; ".join(str(item) for item in fixes)
    return "\n".join(
        part
        for part in (
            f"Incident: {record.get('title', '')}",
            f"Description: {record.get('description', '')}",
            f"Root cause: {record.get('likely_cause', '')}",
            f"Resolution: {fixes}",
        )
        if part.strip()
    )


class IncidentHistoryService:
    def __init__(self, repository: IncidentHistoryRepository, embedding_client=None):
        self.repository = repository
        self.embedding_client = embedding_client or IncidentEmbeddingClient()

    def index_resolved(self, incident_id: int) -> bool:
        if not settings.incident_history_enabled or not settings.openrouter_api_key:
            return False
        record = self.repository.get_resolved_diagnosis(incident_id)
        if record is None:
            return False
        vector = self.embedding_client.embed(_document(record))
        self.repository.save_embedding(incident_id, vector)
        return True

    def index_unindexed_resolved(self, *, limit: int = 500) -> int:
        if not settings.incident_history_enabled or not settings.openrouter_api_key:
            return 0
        records = self.repository.get_unindexed_resolved_diagnoses(limit=limit)
        if not records:
            return 0
        vectors = self.embedding_client.embed_many([_document(record) for record in records])
        self.repository.save_embeddings(
            {record["incident_id"]: vector for record, vector in zip(records, vectors, strict=True)}
        )
        return len(records)

    def find_similar(self, incident: dict, evidence: list[dict]) -> list[dict]:
        if (
            not settings.incident_history_enabled
            or not settings.openrouter_api_key
            or not self.repository.has_embeddings()
        ):
            return []
        excerpt = [
            f"{item.get('level', '')}: {str(item.get('message', ''))[:200]}"
            for item in evidence[:20]
        ]
        query = "\n".join(
            part
            for part in (
                f"Incident: {incident.get('title', '')}",
                f"Description: {incident.get('description') or ''}",
                *excerpt,
            )
            if part.strip()
        )
        if not query.strip():
            return []
        vector = self.embedding_client.embed(query)
        matches = self.repository.search(
            vector,
            limit=settings.incident_history_limit,
            floor=settings.incident_history_similarity_floor,
        )
        now = datetime.now(UTC)
        for match in matches:
            resolved_at = match.get("resolved_at")
            if resolved_at is None:
                match["days_since_resolution"] = None
                continue
            if resolved_at.tzinfo is None:
                resolved_at = resolved_at.replace(tzinfo=UTC)
            match["days_since_resolution"] = max((now - resolved_at).days, 0)
        return matches
