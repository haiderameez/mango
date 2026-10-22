"""The log intake endpoint only authenticates and enqueues bounded batches."""
import base64

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database.session import get_db
from app.services.ingest_service import IngestService
from app.tasks import process_ingest_batch

router = APIRouter(prefix="/ingest", tags=["log ingestion"])
MAX_COMPRESSED_BYTES = 1_000_000


def enqueue_ingest_batch(key_id: int, payload: bytes, compressed: bool) -> None:
    """Queue batch bytes for the separate ingestion worker."""
    process_ingest_batch.apply_async(
        args=(key_id, base64.b64encode(payload).decode("ascii"), compressed),
        queue="ingestion",
    )


@router.post("/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_logs(
    request: Request,
    ingest_key: str | None = Header(default=None, alias="X-Ingest-Key"),
    db: Session = Depends(get_db),
):
    if not ingest_key:
        raise HTTPException(status_code=401, detail="A valid X-Ingest-Key is required.")
    key = await run_in_threadpool(IngestService(db).authenticate, ingest_key)
    if key is None:
        raise HTTPException(status_code=401, detail="A valid X-Ingest-Key is required.")
    key_id = key.id
    # Do not hold a database connection while a client streams a large batch.
    await run_in_threadpool(db.close)

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

    await run_in_threadpool(enqueue_ingest_batch, key_id, payload, encoding == "gzip")
    return {"status": "accepted"}
