"""The log intake endpoint only authenticates and enqueues bounded batches."""
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database.session import SessionLocal, get_db
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/ingest", tags=["log ingestion"])
MAX_COMPRESSED_BYTES = 1_000_000


def process_ingest_batch(key_id: int, payload: bytes, compressed: bool) -> None:
    """Background entry point owns its session; ingestion never couples to HTTP session."""
    with SessionLocal() as db:
        IngestService(db).process_batch(key_id, payload, compressed)


@router.post("/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_logs(
    request: Request,
    background_tasks: BackgroundTasks,
    ingest_key: str | None = Header(default=None, alias="X-Ingest-Key"),
    db: Session = Depends(get_db),
):
    if not ingest_key:
        raise HTTPException(status_code=401, detail="A valid X-Ingest-Key is required.")
    key = IngestService(db).authenticate(ingest_key)
    if key is None:
        raise HTTPException(status_code=401, detail="A valid X-Ingest-Key is required.")

    encoding = request.headers.get("content-encoding", "identity").lower()
    if encoding not in {"identity", "gzip"}:
        raise HTTPException(
            status_code=415,
            detail="Only identity or gzip content encoding is supported.",
        )
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_COMPRESSED_BYTES:
            raise HTTPException(status_code=413, detail="Compressed batch exceeds 1 MB.")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if not payload:
        raise HTTPException(status_code=400, detail="Batch cannot be empty.")

    background_tasks.add_task(process_ingest_batch, key.id, payload, encoding == "gzip")
    return {"status": "accepted"}
