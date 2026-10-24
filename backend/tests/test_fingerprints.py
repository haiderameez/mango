from app.services.fingerprint import failure_fingerprint, normalize_message


def test_message_normalization_collapses_ips_ids_timestamps_and_numbers():
    first = "connect to 10.0.3.17:5432 failed at 2026-10-22T10:20:30Z id=81"
    second = "connect to 10.0.4.2:6432 failed at 2026-11-23T11:21:31Z id=95"

    assert normalize_message(first) == normalize_message(second)


def test_fingerprint_changes_for_a_different_service_or_error_type():
    base = failure_fingerprint("checkout", "connection failed", "OperationalError")

    assert base != failure_fingerprint("payments", "connection failed", "OperationalError")
    assert base != failure_fingerprint("checkout", "connection failed", "TimeoutError")


def test_message_normalization_collapses_numbers_attached_to_units():
    assert normalize_message("query timed out after 5ms") == normalize_message(
        "query timed out after 31ms"
    )
