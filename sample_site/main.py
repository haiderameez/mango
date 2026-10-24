"""Night Window Coffee, a small independent service wired to Mango log ingestion."""
import json
import os
import threading
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

SERVICE_NAME = os.getenv("SERVICE_NAME", "night-window-coffee")
MANGO_URL = os.getenv("MANGO_URL", "http://localhost:8000").rstrip("/")
MANGO_INGEST_KEY = os.getenv("MANGO_INGEST_KEY", "")
LOG_PATH = Path(os.getenv("LOG_PATH", "logs/night-window.jsonl"))
PAGE_PATH = Path(__file__).parent / "index.html"
PRODUCTS = {"night-blend": "Night Blend", "early-light": "Early Light"}
_file_lock = threading.Lock()


class OrderRequest(BaseModel):
    product: str = "night-blend"
    quantity: int = Field(default=1, ge=1, le=8)
    simulate_failure: bool = False


def _write_log(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock, LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(event, separators=(",", ":")) + "\n")


def create_app(mango_sender=None) -> FastAPI:
    app = FastAPI(title="Night Window Coffee", docs_url=None, redoc_url=None)
    app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "assets"), name="assets")
    app.state.events = deque(maxlen=12)
    app.state.delivery = {"accepted": 0, "failed": 0, "last_status": "waiting"}

    def send_to_mango(event: dict) -> None:
        if not MANGO_INGEST_KEY:
            app.state.delivery["last_status"] = "key not configured"
            return
        try:
            response = httpx.post(
                f"{MANGO_URL}/ingest/logs",
                content=json.dumps(event, separators=(",", ":")) + "\n",
                headers={
                    "X-Ingest-Key": MANGO_INGEST_KEY,
                    "Content-Type": "application/x-ndjson",
                },
                timeout=10,
            )
            response.raise_for_status()
            app.state.delivery["accepted"] += 1
            app.state.delivery["last_status"] = "accepted"
        except httpx.HTTPError as error:
            app.state.delivery["failed"] += 1
            app.state.delivery["last_status"] = type(error).__name__

    app.state.mango_sender = mango_sender or send_to_mango

    @app.middleware("http")
    async def request_id_header(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.get("/", include_in_schema=False)
    def storefront():
        return FileResponse(PAGE_PATH)

    @app.get("/api/state")
    def state():
        return {
            "service": SERVICE_NAME,
            "mango_url": MANGO_URL,
            "key_configured": bool(MANGO_INGEST_KEY),
            "delivery": dict(app.state.delivery),
            "events": list(app.state.events),
        }

    @app.post("/api/orders")
    def place_order(order: OrderRequest, request: Request, background_tasks: BackgroundTasks):
        product = PRODUCTS.get(order.product)
        if product is None:
            return JSONResponse(status_code=422, content={"detail": "Choose a listed roast."})

        failed = order.simulate_failure
        message = (
            "Checkout failed: simulated payment gateway unavailable"
            if failed
            else f"Order accepted: {order.quantity} bag(s) of {product}"
        )
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service": SERVICE_NAME,
            "level": "ERROR" if failed else "INFO",
            "message": message,
            "request_id": request.state.request_id,
            "route": "POST /api/orders",
            "error_type": "PaymentGatewayUnavailable" if failed else None,
            "product": product,
            "quantity": order.quantity,
        }
        _write_log(event)
        app.state.events.appendleft(event)
        background_tasks.add_task(app.state.mango_sender, event)

        if failed:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "payment unavailable",
                    "request_id": event["request_id"],
                    "message": "The payment service is unavailable. The order was not placed.",
                },
            )
        return {"status": "accepted", "product": product, "quantity": order.quantity}

    return app


app = create_app()
