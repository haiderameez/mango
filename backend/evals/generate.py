"""Generate fixed synthetic fixtures from DummyCommerce's executable fault table."""

import json
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = Path(__file__).parent / "scenarios"

# Ground truth is author-specified, never inferred from the model's output.
# Service means owner of the fault, not necessarily the service emitting the log.
ANSWERS = {
    "db_connection": (
        "dependency",
        "orders-db",
        "orders-db refuses connections",
        "Restore database connectivity and verify the listener and health check.",
    ),
    "dependency_down": (
        "dependency",
        "payments.internal",
        "payment upstream returns HTTP 503",
        "Restore payment upstream availability and verify circuit recovery.",
    ),
    "memory_pressure": (
        "resource_exhaustion",
        "dummycommerce",
        "order worker exceeds memory limit",
        "Reduce worker memory use or increase its memory limit; verify no OOMs.",
    ),
    "disk_full": (
        "resource_exhaustion",
        "orders-db",
        "database data volume is full",
        "Free or expand database storage and verify WAL writes.",
    ),
    "internal_error": (
        "code_defect",
        "dummycommerce",
        "pricing multiplies a missing discount rate",
        "Handle missing promotion results before performing pricing arithmetic.",
    ),
    "missing_field": (
        "code_defect",
        "dummycommerce",
        "serializer indexes an absent optional field",
        "Handle absent shipping_address in the order serializer.",
    ),
    "invalid_credentials": (
        "config",
        "dummycommerce",
        "application uses stale database credentials",
        "Deploy the current database credential and verify authentication.",
    ),
    "invalid_endpoint": (
        "config",
        "dummycommerce",
        "payment client hostname is misspelled",
        "Correct PAYMENT_URL to payments.internal and verify resolution.",
    ),
    "slow": (
        "latency",
        "orders-db",
        "missing order_id index causes a slow sequential scan",
        "Add an index on order_items.order_id and verify query plan and latency.",
    ),
    "lock_contention": (
        "latency",
        "orders-db",
        "uncommitted transaction blocks order updates",
        "End the blocking transaction and shorten transaction lifetimes.",
    ),
}
VARIANTS = ("clean", "noise", "sparse", "distractors", "outside_window")


def generate(destination: Path = SCENARIOS) -> None:
    faults = runpy.run_path(str(ROOT / "dummycommerce" / "faults.py"))["FAULTS"]
    destination.mkdir(parents=True, exist_ok=True)
    for family_index, (family, answer) in enumerate(ANSWERS.items()):
        for variant_index, variant in enumerate(VARIANTS):
            # Interleave families so an early quota-limited batch is not one repeated fault.
            number = variant_index * len(ANSWERS) + family_index + 1
            scenario_id = f"case-{number:02d}"
            now = datetime(2026, 10, 1, 12, tzinfo=UTC) + timedelta(days=number)
            fault = faults[family]
            events = fault["events"][-1:] if variant == "sparse" else fault["events"]
            records = []
            for index, (level, message, fields) in enumerate(events):
                records.append(
                    {
                        "timestamp": (now - timedelta(seconds=30 - index)).isoformat(),
                        "level": level,
                        "message": message,
                        "service": "dummycommerce",
                        "endpoint": "POST /orders",
                        "request_id": f"request-{number:02d}",
                        **fields,
                    }
                )
            for index in range(12 if variant != "clean" else 0):
                records.append(
                    {
                        "timestamp": (now - timedelta(seconds=60 + index)).isoformat(),
                        "level": "INFO",
                        "message": "Product listing completed",
                        "service": "catalog",
                        "request_id": f"unrelated-{index}",
                    }
                )
            if variant in {"distractors", "outside_window"}:
                records.append(
                    {
                        "timestamp": (
                            now - timedelta(minutes=60 if variant == "outside_window" else 2)
                        ).isoformat(),
                        "level": "ERROR",
                        "message": "analytics export request timed out",
                        "service": "analytics",
                        "request_id": "unrelated-export",
                    }
                )
            # No fault identifier, answer key, fix, or expected category enters evidence.
            (destination / f"{scenario_id}.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8"
            )
            key = {
                "id": scenario_id,
                "family": family,
                "variant": variant,
                "incident": {
                    "id": number,
                    "title": "Order requests failing or degraded",
                    "description": f"Investigate POST /orders, request_id=request-{number:02d}.",
                    "severity": fault["severity"],
                    "status": "OPEN",
                    "created_at": now.isoformat(),
                },
                "category": answer[0],
                "service": answer[1],
                "root_cause": answer[2],
                "fix": answer[3],
            }
            (destination / f"{scenario_id}.yaml").write_text(
                yaml.safe_dump(key, sort_keys=False), encoding="utf-8"
            )


if __name__ == "__main__":
    generate()
