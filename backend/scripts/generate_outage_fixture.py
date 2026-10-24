"""Generate the deterministic 10k-record fixture used by the dedup replay."""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "load" / "outage.jsonl"
EXPECTED = ROOT / "load" / "outage.expected.json"
FAULTS = (
    ("OperationalError", "orders database connection refused from 10.0.{n}.17:5432"),
    ("UpstreamError", "payment provider returned HTTP {status}"),
    ("MemoryError", "worker OutOfMemory during image processing"),
    ("AuthError", "token issuer rejected credentials for client {n}"),
    ("TimeoutError", "inventory query timed out against catalog-db after {n}ms"),
    ("TypeError", "checkout handler raised TypeError in order serializer"),
)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    start = datetime.now(UTC)
    failures = 0
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        for index in range(10_000):
            ts = start + timedelta(milliseconds=index)
            is_failure = index % 25 == 0
            item = {
                "timestamp": ts.isoformat(),
                "service": "outage-test",
                "level": "ERROR" if is_failure else "INFO",
                "message": "routine health check passed",
                "request_id": f"req-{index:05d}",
            }
            if is_failure:
                fault_id = failures % len(FAULTS)
                error_type, template = FAULTS[fault_id]
                item["message"] = template.format(n=(failures % 31) + 1,
                                                   status=500 + (failures % 3))
                item["error_type"] = error_type
                item["upstream_name"] = f"outage-dependency-{fault_id}"
                failures += 1
            handle.write(json.dumps(item, separators=(",", ":")) + "\n")
    EXPECTED.write_text(
        json.dumps({"records": 10_000, "failures": failures, "incidents": 6}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT} ({10_000} records, {failures} failures, 6 expected incidents)")


if __name__ == "__main__":
    main()
