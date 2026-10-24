from evals.history_seed import history_records


def test_history_seed_contains_fifty_distinct_resolved_examples():
    records = history_records()

    assert len(records) == 50
    assert len({record["seed_id"] for record in records}) == 50
    assert len({record["title"] for record in records}) == 50
    assert all(record["likely_cause"] and record["resolution"] for record in records)


def test_history_seed_is_independent_of_benchmark_answer_key_files():
    records = history_records()

    assert not any(record["seed_id"].startswith("case-") for record in records)
    assert all("category" not in record and "variant" not in record for record in records)
