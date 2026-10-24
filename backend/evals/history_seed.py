"""Independent synthetic resolved cases for exercising semantic history retrieval."""

from datetime import UTC, datetime, timedelta

# Each family contributes five differently phrased historical incidents. This fixture is
# independent of the benchmark YAML answer files and exists only as prior resolved history.
_FAMILIES = (
    (
        "orders-db",
        "orders database connections",
        "connection refused on the PostgreSQL listener",
        "The database process restarted but its listener did not become ready.",
        "Restore PostgreSQL, verify port 5432 is listening, and confirm the health check passes.",
    ),
    (
        "payments.internal",
        "payment authorizations",
        "HTTP 503 responses from the payment provider",
        "The payment upstream returned service unavailable during authorization requests.",
        "Restore provider availability, verify the circuit closes, and retry with bounded backoff.",
    ),
    (
        "dummycommerce",
        "order worker memory",
        "container memory limit exceeded before the worker restarted",
        "The order worker exceeded its memory limit and the OOM killer terminated it.",
        "Reduce per-request memory or raise the limit, then verify usage under "
        "representative load.",
    ),
    (
        "orders-db",
        "database volume capacity",
        "no space left on device while writing data and WAL",
        "The database volume ran out of free space, preventing writes and WAL growth.",
        "Free or expand storage, verify WAL advances, and confirm writes resume without errors.",
    ),
    (
        "dummycommerce",
        "checkout pricing calculation",
        "TypeError after a missing promotion rate reached arithmetic",
        "The pricing path multiplied a missing promotion result instead of handling no discount.",
        "Handle an absent promotion result before arithmetic and add a no-discount "
        "regression test.",
    ),
    (
        "dummycommerce",
        "order shipping address serialization",
        "missing-key error when an optional shipping address was omitted",
        "The serializer indexed shipping_address even though the field is optional.",
        "Treat shipping_address as optional and test requests with and without that field.",
    ),
    (
        "dummycommerce",
        "application database authentication",
        "password authentication failure after a credential rotation",
        "Application workers kept an old database password after the secret was rotated.",
        "Deploy the current credential through the secret store, restart workers, and "
        "verify login.",
    ),
    (
        "dummycommerce",
        "payment endpoint resolution",
        "DNS lookup failure for the configured payment hostname",
        "The payment client used a misspelled hostname that does not exist in internal DNS.",
        "Correct PAYMENT_URL to payments.internal and verify resolution from the app network.",
    ),
    (
        "orders-db",
        "order item lookup latency",
        "a sequential scan on order_items for every order_id lookup",
        "The order_items.order_id predicate lacked an index, forcing full-table scans.",
        "Index order_items.order_id, compare query plans, and verify latency under "
        "representative load.",
    ),
    (
        "orders-db",
        "order update lock waits",
        "writes blocked behind a long-running uncommitted transaction",
        "A transaction held row locks without committing and blocked concurrent order updates.",
        "End the blocking transaction, shorten transaction lifetimes, and track lock wait "
        "duration.",
    ),
)

_VARIANTS = (
    ("{subject} failed after a recent change", "Requests fail because {signal}."),
    ("Requests are failing in {subject}", "Monitoring reports {signal} in the affected service."),
    (
        "Repeated failures affecting {subject}",
        "Logs show {signal}; retries have not restored service.",
    ),
    ("{subject} is degraded", "The application is responsive, but {signal} continues."),
    (
        "Investigating an incident with {subject}",
        "The failure signature is {signal} during the incident.",
    ),
)


def history_records() -> list[dict[str, str]]:
    """Return 50 synthetic historical diagnoses, separate from benchmark answer files."""
    now = datetime.now(UTC)
    records = []
    for family_index, (service, subject, signal, cause, resolution) in enumerate(_FAMILIES):
        for variant_index, (title_pattern, description_pattern) in enumerate(_VARIANTS):
            number = family_index * len(_VARIANTS) + variant_index + 1
            records.append(
                {
                    "seed_id": f"history-{number:02d}",
                    "service": service,
                    "title": title_pattern.format(subject=subject),
                    "description": description_pattern.format(signal=signal),
                    "likely_cause": cause,
                    "resolution": resolution,
                    "resolved_at": (now - timedelta(days=number)).isoformat(),
                }
            )
    return records
