from app.models.ingest import DetectionRule
from scripts.provision_night_window_site import ensure_detection_rule


def test_provisioning_adds_a_rule_for_three_matching_checkout_failures(db):
    created = ensure_detection_rule(db)

    rule = db.query(DetectionRule).one()
    assert created is True
    assert rule.service == "night-window-coffee"
    assert rule.level == "ERROR"
    assert rule.threshold == 3
    assert rule.window_seconds == 60
    assert rule.pattern == "simulated payment gateway unavailable"


def test_provisioning_does_not_duplicate_the_checkout_failure_rule(db):
    assert ensure_detection_rule(db) is True

    assert ensure_detection_rule(db) is False
    assert db.query(DetectionRule).count() == 1
