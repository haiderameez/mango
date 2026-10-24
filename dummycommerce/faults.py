# Faults that can be armed.
#
# A real failure is never one log line. Each fault emits the sequence a real application
# would leave behind - the warnings leading up to it, the retries, the failure itself and
# the after-effects - because an investigation is only as good as the evidence it gets.
# "events" is (level, message, extra fields); the last one is the failure proper.
FAULTS = {
    "memory_pressure": {
        "status": 503, "error_type": "MemoryError", "severity": "CRITICAL",
        "title": "Order worker unavailable",
        "events": [
            ("WARNING", "order worker RSS 510MiB approaches container limit 512MiB", {}),
            ("ERROR", "allocation failed in order worker: MemoryError", {}),
            ("ERROR", "order worker terminated: OOMKilled, exit 137", {}),
        ],
    },
    "disk_full": {
        "status": 500, "error_type": "OSError", "severity": "CRITICAL",
        "title": "Order persistence failing",
        "events": [
            ("WARNING", "orders-db data volume utilization 100%, free bytes 0", {}),
            ("ERROR", "orders-db cannot extend WAL: No space left on device", {}),
            ("ERROR", "transaction aborted because orders-db storage is full", {}),
        ],
    },
    "missing_field": {
        "status": 500, "error_type": "KeyError", "severity": "HIGH",
        "title": "Order serialization failing",
        "events": [
            ("WARNING", "legacy order payload lacks optional shipping_address field", {}),
            ("ERROR", "serializer.py line 31: address = order['shipping_address']", {}),
            ("ERROR", "KeyError: shipping_address in order serializer", {}),
        ],
    },
    "invalid_credentials": {
        "status": 500, "error_type": "AuthenticationError", "severity": "HIGH",
        "title": "Order database authentication failing",
        "events": [
            ("WARNING", "deployment loaded stale database credential version v1; expected v2", {}),
            ("ERROR", "orders-db authentication failed for application user", {}),
            ("ERROR", "order writer rejected: configured database password is out of date", {}),
        ],
    },
    "invalid_endpoint": {
        "status": 502, "error_type": "NameResolutionError", "severity": "HIGH",
        "title": "Payment requests failing",
        "events": [
            ("WARNING", "PAYMENT_URL configured as https://paymnts.internal/charge", {}),
            ("ERROR", "DNS NXDOMAIN for paymnts.internal; expected host payments.internal", {}),
            ("ERROR", "payment client cannot resolve configured upstream hostname", {}),
        ],
    },
    "lock_contention": {
        "status": 504, "error_type": "LockTimeout", "severity": "HIGH",
        "title": "Order updates timing out",
        "events": [
            ("WARNING", "orders-db UPDATE orders waiting 5000ms on row lock", {}),
            ("WARNING", "orders-db blocking transaction idle in transaction for 120s", {}),
            ("ERROR", "orders-db lock timeout: order update blocked by uncommitted transaction", {}),
        ],
    },
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
