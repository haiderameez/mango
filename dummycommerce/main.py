"""DummyCommerce: a tiny e-commerce API that fails on demand.

It writes structured JSONL logs (which Mango reads as evidence) and reports failures to
Mango's incident API.

    uvicorn main:app --port 8001

Arm a fault, then hit the endpoint it affects:

    curl -X POST localhost:8001/faults/db_connection
    curl -X POST localhost:8001/orders -H "content-type: application/json" \
        -d '{"product_id": 1, "quantity": 2}'
"""
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

LOG_PATH = Path(os.getenv("LOG_PATH", Path(__file__).parent / "logs" / "app.jsonl"))

MANGO_API_URL = os.getenv("MANGO_API_URL", "http://localhost:8000")
MANGO_EMAIL = os.getenv("MANGO_EMAIL", "")
MANGO_PASSWORD = os.getenv("MANGO_PASSWORD", "")

SERVICE = "dummycommerce"

PRODUCTS = [
    {"id": 1, "name": "Mango crate", "price": 24.0, "stock": 12},
    {"id": 2, "name": "Mango juice", "price": 4.5, "stock": 240},
    {"id": 3, "name": "Dried mango", "price": 7.25, "stock": 0},
]

# Faults that can be armed.
#
# A real failure is never one log line. Each fault emits the sequence a real application
# would leave behind - the warnings leading up to it, the retries, the failure itself and
# the after-effects - because an investigation is only as good as the evidence it gets.
# "events" is (level, message, extra fields); the last one is the failure proper.
FAULTS = {
    "db_connection": {
        "status": 500,
        "error_type": "OperationalError",
        "severity": "CRITICAL",
        "title": "Order creation failing: orders-db connection refused",
        "events": [
            ("WARNING", "connection pool for orders-db exhausted: 10/10 in use, 4 waiters",
             {"pool_size": 10, "pool_in_use": 10, "pool_waiters": 4}),
            ("WARNING", "checkout of a pooled connection timed out after 2000ms, opening a new one",
             {"duration_ms": 2000}),
            ("WARNING", 'connection to "orders-db" (10.0.3.17:5432) failed, retry 1/3 in 200ms',
             {"retry": 1, "error_type": "OperationalError"}),
            ("WARNING", 'connection to "orders-db" (10.0.3.17:5432) failed, retry 2/3 in 400ms',
             {"retry": 2, "error_type": "OperationalError"}),
            ("ERROR", "health check db:orders-db failed: no route to 10.0.3.17:5432",
             {"check": "db:orders-db", "error_type": "HealthCheckFailed"}),
            ("ERROR",
             'could not connect to server: Connection refused. Is the server running on host '
             '"orders-db" (10.0.3.17) and accepting TCP/IP connections on port 5432?',
             {"error_type": "OperationalError", "retry": 3}),
        ],
    },
    "dependency_down": {
        "status": 502,
        "error_type": "PaymentGatewayUnavailable",
        "severity": "HIGH",
        "title": "Order creation failing: payment gateway unavailable",
        "events": [
            ("INFO", "POST https://payments.internal/charge attempt 1/3",
             {"upstream": "payments.internal"}),
            ("WARNING", "payments.internal returned HTTP 503 in 1500ms (attempt 1/3)",
             {"upstream": "payments.internal", "upstream_status": 503, "duration_ms": 1500}),
            ("WARNING", "payments.internal returned HTTP 503 in 1500ms (attempt 2/3)",
             {"upstream": "payments.internal", "upstream_status": 503, "duration_ms": 1500}),
            ("WARNING", "circuit breaker for payments.internal moved to HALF_OPEN after 2 failures",
             {"upstream": "payments.internal", "circuit_state": "HALF_OPEN"}),
            ("ERROR", "POST https://payments.internal/charge failed: HTTP 503 after 3 retries",
             {"upstream": "payments.internal", "upstream_status": 503,
              "error_type": "PaymentGatewayUnavailable"}),
            ("ERROR", "circuit breaker for payments.internal is OPEN, failing fast for 30s",
             {"upstream": "payments.internal", "circuit_state": "OPEN"}),
        ],
    },
    "internal_error": {
        "status": 500,
        "error_type": "TypeError",
        "severity": "HIGH",
        "title": "Order creation failing: unhandled TypeError in pricing",
        "events": [
            ("WARNING", "promo lookup for code PROMO_EXPIRED returned no rows, discount_rate=None",
             {"promo_code": "PROMO_EXPIRED"}),
            ("ERROR",
             'Traceback (most recent call last): File "pricing.py", line 48, in total  '
             "return subtotal * discount_rate",
             {"error_type": "TypeError", "module": "pricing"}),
            ("ERROR", "unsupported operand type(s) for *: 'NoneType' and 'int' in pricing.total()",
             {"error_type": "TypeError", "module": "pricing"}),
        ],
    },
    "slow": {
        "status": 200,
        "error_type": "SlowResponse",
        "severity": "MEDIUM",
        "title": "Order creation degraded: responses above latency threshold",
        "events": [
            ("WARNING",
             "slow query 2900ms: SELECT * FROM order_items WHERE order_id = $1 "
             "(seq scan, no index on order_id)",
             {"duration_ms": 2900, "table": "order_items", "plan": "Seq Scan"}),
            ("WARNING", "inventory lookup took 3100ms (threshold 500ms)",
             {"duration_ms": 3100}),
            ("WARNING", "order created but took 3200ms (threshold 500ms)",
             {"duration_ms": 3200, "error_type": "SlowResponse"}),
        ],
    },
}

armed_fault: str | None = None

app = FastAPI(title="DummyCommerce", version="1.0.0")
faults_router = APIRouter(prefix="/faults", tags=["faults"])


class OrderRequest(BaseModel):
    product_id: int
    quantity: int = 1


def log(level: str, message: str, **fields) -> None:
    """Append one structured record. This file is Mango's evidence source."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "service": SERVICE,
        "message": message,
        **fields,
    }

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def report_incident(title: str, description: str, severity: str, request_id: str) -> None:
    """Create an incident in Mango and ask it to investigate. Best-effort by design: the
    detector must not crash the application it is watching."""
    if not (MANGO_EMAIL and MANGO_PASSWORD):
        log(
            "WARNING",
            "Mango credentials not configured, incident not reported",
            request_id=request_id,
        )
        return

    try:
        with httpx.Client(base_url=MANGO_API_URL, timeout=10) as client:
            login = client.post(
                "/auth/login", json={"email": MANGO_EMAIL, "password": MANGO_PASSWORD}
            )
            login.raise_for_status()
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            created = client.post(
                "/incidents",
                json={
                    "title": title,
                    "description": f"{description} (request_id={request_id})",
                    "severity": severity,
                },
                headers=headers,
            )
            created.raise_for_status()
            incident_id = created.json()["id"]

            client.post(f"/incidents/{incident_id}/investigate", headers=headers)

        log("INFO", f"Reported incident #{incident_id} to Mango", request_id=request_id)

    except Exception as error:
        log(
            "WARNING",
            f"Failed to report incident to Mango: {error.__class__.__name__}",
            request_id=request_id,
        )


@app.get("/health", tags=["operations"])
def health():
    return {"status": "ok", "armed_fault": armed_fault}


@app.get("/products", tags=["shop"])
def list_products():
    request_id = uuid.uuid4().hex[:12]
    log("INFO", "Listed products", endpoint="GET /products", request_id=request_id)
    return PRODUCTS


@app.post("/orders", tags=["shop"], status_code=201)
def create_order(order: OrderRequest):
    request_id = uuid.uuid4().hex[:12]
    endpoint = "POST /orders"

    product = next((p for p in PRODUCTS if p["id"] == order.product_id), None)

    if product is None:
        log("WARNING", "Unknown product", endpoint=endpoint, request_id=request_id)
        raise HTTPException(status_code=404, detail="Product not found.")

    if armed_fault:
        fault = FAULTS[armed_fault]

        if armed_fault == "slow":
            time.sleep(3.2)

        # The whole sequence shares one request id, which is what makes the evidence
        # traceable back to a single failed request.
        for level, message, extra in fault["events"]:
            log(
                level,
                message,
                endpoint=endpoint,
                request_id=request_id,
                fault=armed_fault,
                **extra,
            )

        failure_message = fault["events"][-1][1]

        report_incident(
            title=fault["title"],
            description=f"{endpoint} returned {fault['status']}: {failure_message}",
            severity=fault["severity"],
            request_id=request_id,
        )

        if fault["status"] >= 500:
            raise HTTPException(status_code=fault["status"], detail="Internal server error.")

    log(
        "INFO",
        f"Created order for product {product['id']} x{order.quantity}",
        endpoint=endpoint,
        request_id=request_id,
    )

    return {
        "order_id": uuid.uuid4().hex[:8],
        "product_id": product["id"],
        "quantity": order.quantity,
        "total": round(product["price"] * order.quantity, 2),
        "request_id": request_id,
    }


@faults_router.post("/{name}")
def arm_fault(name: str):
    global armed_fault

    if name not in FAULTS:
        raise HTTPException(status_code=404, detail=f"Unknown fault. Known: {sorted(FAULTS)}")

    armed_fault = name
    log("WARNING", f"Fault armed: {name}", endpoint=f"POST /faults/{name}")

    return {"armed_fault": armed_fault}


@faults_router.delete("")
def clear_faults():
    global armed_fault

    armed_fault = None
    log("INFO", "Faults cleared", endpoint="DELETE /faults")

    return {"armed_fault": None}


app.include_router(faults_router)
