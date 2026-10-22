import pytest

from app.ai import graph, quota
from app.core.config import settings
from app.core.exceptions import LlmQuotaExhaustedError
from app.services.incident_embeddings import EMBEDDINGS_URL, IncidentEmbeddingClient
from app.services.incident_history import IncidentHistoryService


class FakeEmbeddingRepository:
    def __init__(self, record=None, matches=None):
        self.record = record
        self.matches = matches or []
        self.saved = []
        self.search_arguments = None

    def get_resolved_diagnosis(self, incident_id):
        return self.record

    def save_embedding(self, incident_id, vector):
        self.saved.append((incident_id, vector))

    def search(self, vector, *, limit, floor):
        self.search_arguments = (vector, limit, floor)
        return self.matches

    def has_embeddings(self):
        return bool(self.matches)


class FakeEmbeddingProvider:
    def __init__(self, vector=None):
        self.vector = vector or [0.25] * 768
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        return self.vector


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class FakeHttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def test_history_search_embeds_incident_and_evidence_and_applies_similarity_settings(
    monkeypatch,
):
    monkeypatch.setattr(settings, "incident_history_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    match = {
        "incident_id": 17,
        "title": "Database pool exhausted",
        "likely_cause": "Connections leaked",
        "fix": ["Recycle workers"],
        "similarity": 0.91,
        "resolved_at": None,
    }
    repository = FakeEmbeddingRepository(matches=[match])
    embeddings = FakeEmbeddingProvider()
    service = IncidentHistoryService(repository, embeddings)

    found = service.find_similar(
        {"title": "Checkout failing", "description": "pool timeout"},
        [{"level": "ERROR", "message": "connection pool exhausted"}],
    )

    assert found == [{**match, "days_since_resolution": None}]
    assert "Checkout failing" in embeddings.calls[0]
    assert "connection pool exhausted" in embeddings.calls[0]
    assert repository.search_arguments == (
        embeddings.vector,
        settings.incident_history_limit,
        settings.incident_history_similarity_floor,
    )


def test_history_indexing_uses_resolved_diagnosis_and_fix(monkeypatch):
    monkeypatch.setattr(settings, "incident_history_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    repository = FakeEmbeddingRepository(
        record={
            "incident_id": 17,
            "title": "Checkout failures",
            "description": "Pool exhaustion",
            "likely_cause": "Connections leaked",
            "fix": ["Recycle workers"],
        }
    )
    embeddings = FakeEmbeddingProvider()
    service = IncidentHistoryService(repository, embeddings)

    assert service.index_resolved(17)
    assert repository.saved == [(17, embeddings.vector)]
    assert "Connections leaked" in embeddings.calls[0]
    assert "Recycle workers" in embeddings.calls[0]


def test_history_indexing_skips_incidents_without_a_completed_diagnosis():
    repository = FakeEmbeddingRepository()
    embeddings = FakeEmbeddingProvider()

    assert not IncidentHistoryService(repository, embeddings).index_resolved(17)
    assert embeddings.calls == []


def test_history_backfill_batches_all_unindexed_incidents(monkeypatch):
    monkeypatch.setattr(settings, "incident_history_enabled", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    repository = FakeEmbeddingRepository()
    records = [
        {"incident_id": number, "title": f"Fault {number}", "likely_cause": "pool"}
        for number in (2, 7)
    ]
    repository.get_unindexed_resolved_diagnoses = lambda *, limit: records[:limit]
    repository.save_embeddings = lambda items: repository.saved.extend(items.items())

    class BatchEmbeddingProvider(FakeEmbeddingProvider):
        def embed_many(self, texts):
            self.calls.extend(texts)
            return [[float(index)] * 768 for index, _text in enumerate(texts)]

    embeddings = BatchEmbeddingProvider()

    assert IncidentHistoryService(repository, embeddings).index_unindexed_resolved(limit=10) == 2
    assert len(embeddings.calls) == 2
    assert [item[0] for item in repository.saved] == [2, 7]


def test_history_node_returns_no_matches_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "incident_history_enabled", False)

    result = graph.history({"incident": {"title": "outage"}}, service=object())

    assert result == {"history": []}


def test_root_cause_prompt_includes_similarity_qualified_prior_art(monkeypatch):
    prompts = []

    class Diagnosis:
        def model_dump(self):
            return {"likely_cause": "current evidence"}

    def capture_prompt(_schema, prompt):
        prompts.append(prompt)
        return Diagnosis()

    monkeypatch.setattr(
        graph,
        "_ask",
        capture_prompt,
    )

    graph.root_cause(
        {
            "incident": {"title": "Checkout errors"},
            "history": [{"incident_id": 3, "likely_cause": "Pool exhausted"}],
        }
    )

    assert "Pool exhausted" in prompts[0]
    assert "Diagnose this incident from its own supplied evidence" in prompts[0]


def test_embedding_request_is_pinned_and_spends_one_guarded_request(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_embedding_model", "openai/text-embedding-3-small")
    monkeypatch.setattr(quota, "is_cooling_down", lambda: False)
    monkeypatch.setattr(quota, "has_capacity", lambda: True)
    monkeypatch.setattr(quota, "wait_for_rate_slot", lambda model: None)
    spent = []
    monkeypatch.setattr(quota, "consume", lambda: spent.append(True) or True)
    client = FakeHttpClient(FakeResponse({"data": [{"index": 0, "embedding": [0.5] * 768}]}))

    vector = IncidentEmbeddingClient(client).embed("pool exhaustion")

    assert len(vector) == 768
    assert spent == [True]
    assert client.calls[0][0] == EMBEDDINGS_URL
    assert client.calls[0][1]["json"] == {
        "model": "openai/text-embedding-3-small",
        "input": ["pool exhaustion"],
        "dimensions": 768,
    }


def test_embedding_request_is_not_sent_when_the_daily_budget_is_spent(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(quota, "is_cooling_down", lambda: False)
    monkeypatch.setattr(quota, "has_capacity", lambda: False)
    client = FakeHttpClient(FakeResponse({}))

    with pytest.raises(LlmQuotaExhaustedError):
        IncidentEmbeddingClient(client).embed("pool exhaustion")

    assert client.calls == []


def test_resolving_an_incident_queues_history_indexing(client, incident, headers, monkeypatch):
    from app.tasks import index_resolved_incident

    queued = []
    monkeypatch.setattr(settings, "incident_history_enabled", True)
    monkeypatch.setattr(
        index_resolved_incident, "delay", lambda incident_id: queued.append(incident_id)
    )

    first = client.patch(
        f"/incidents/{incident['id']}/status",
        json={"status": "INVESTIGATING"},
        headers=headers,
    )
    second = client.patch(
        f"/incidents/{incident['id']}/status",
        json={"status": "RESOLVED"},
        headers=headers,
    )

    assert first.status_code == second.status_code == 200
    assert queued == [incident["id"]]

