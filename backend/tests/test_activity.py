def activity_types(client, headers, incident_id):
    response = client.get(f"/incidents/{incident_id}/activity", headers=headers)
    assert response.status_code == 200, response.text
    return [entry["activity_type"] for entry in response.json()]


def test_creating_an_incident_records_activity(client, incident, headers):
    body = client.get(f"/incidents/{incident['id']}/activity", headers=headers).json()

    assert len(body) == 1
    assert body[0]["activity_type"] == "INCIDENT_CREATED"
    assert body[0]["user_id"] == client.get("/auth/me", headers=headers).json()["id"]
    assert "HIGH" in body[0]["detail"]


def test_assignment_records_assigned_then_reassigned(client, incident, headers, other_headers):
    target = client.get("/auth/me", headers=other_headers).json()["id"]
    mine = client.get("/auth/me", headers=headers).json()["id"]

    client.patch(
        f"/incidents/{incident['id']}/assign", json={"assigned_to": target}, headers=headers
    )
    client.patch(
        f"/incidents/{incident['id']}/assign", json={"assigned_to": mine}, headers=headers
    )

    assert activity_types(client, headers, incident["id"]) == [
        "INCIDENT_CREATED",
        "ASSIGNED",
        "REASSIGNED",
    ]


def test_status_change_records_the_transition(client, incident, headers):
    client.patch(
        f"/incidents/{incident['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    body = client.get(f"/incidents/{incident['id']}/activity", headers=headers).json()

    assert body[-1]["activity_type"] == "STATUS_CHANGED"
    assert body[-1]["detail"] == "OPEN -> INVESTIGATING"


def test_comment_records_activity(client, incident, headers):
    client.post(
        f"/incidents/{incident['id']}/comments", json={"content": "on it"}, headers=headers
    )

    assert activity_types(client, headers, incident["id"]) == [
        "INCIDENT_CREATED",
        "COMMENT_ADDED",
    ]


def test_editing_or_deleting_a_comment_records_nothing_extra(client, incident, headers):
    created = client.post(
        f"/incidents/{incident['id']}/comments", json={"content": "on it"}, headers=headers
    ).json()

    client.patch(f"/comments/{created['id']}", json={"content": "edited"}, headers=headers)
    client.delete(f"/comments/{created['id']}", headers=headers)

    assert activity_types(client, headers, incident["id"]) == [
        "INCIDENT_CREATED",
        "COMMENT_ADDED",
    ]


def test_a_rejected_status_change_records_no_activity(client, incident, headers):
    response = client.patch(
        f"/incidents/{incident['id']}/status", json={"status": "RESOLVED"}, headers=headers
    )

    assert response.status_code == 403
    assert activity_types(client, headers, incident["id"]) == ["INCIDENT_CREATED"]


def test_a_rejected_assignment_records_no_activity(client, incident, headers, other_headers):
    response = client.patch(
        f"/incidents/{incident['id']}/assign", json={"assigned_to": 9999}, headers=headers
    )

    assert response.status_code == 404
    assert activity_types(client, headers, incident["id"]) == ["INCIDENT_CREATED"]


def test_an_unauthorized_assignment_records_no_activity(client, incident, other_headers):
    target = client.get("/auth/me", headers=other_headers).json()["id"]

    response = client.patch(
        f"/incidents/{incident['id']}/assign",
        json={"assigned_to": target},
        headers=other_headers,
    )

    assert response.status_code == 403
    assert activity_types(client, other_headers, incident["id"]) == ["INCIDENT_CREATED"]


def test_a_rejected_comment_records_no_activity(client, headers, db):
    from app.models.activity import Activity

    assert client.post(
        "/incidents/404/comments", json={"content": "nope"}, headers=headers
    ).status_code == 404
    assert db.query(Activity).count() == 0


def test_activity_is_returned_in_chronological_order(client, incident, headers):
    for _ in range(3):
        client.post(
            f"/incidents/{incident['id']}/comments", json={"content": "x"}, headers=headers
        )

    body = client.get(f"/incidents/{incident['id']}/activity", headers=headers).json()

    assert [entry["id"] for entry in body] == sorted(entry["id"] for entry in body)
    assert [entry["created_at"] for entry in body] == sorted(
        entry["created_at"] for entry in body
    )


def test_activity_requires_authentication(client, incident):
    assert client.get(f"/incidents/{incident['id']}/activity").status_code == 401


def test_activity_for_missing_incident_returns_404(client, headers):
    assert client.get("/incidents/404/activity", headers=headers).status_code == 404


def test_activity_is_scoped_to_its_incident(client, headers):
    first = client.post(
        "/incidents", json={"title": "a", "severity": "LOW"}, headers=headers
    ).json()
    second = client.post(
        "/incidents", json={"title": "b", "severity": "LOW"}, headers=headers
    ).json()

    client.post(f"/incidents/{second['id']}/comments", json={"content": "x"}, headers=headers)

    assert activity_types(client, headers, first["id"]) == ["INCIDENT_CREATED"]
    assert activity_types(client, headers, second["id"]) == ["INCIDENT_CREATED", "COMMENT_ADDED"]


def test_deleting_an_incident_cascades_to_its_activity(client, incident, headers, db):
    from app.models.activity import Activity
    from app.models.incident import Incident

    db.delete(db.get(Incident, incident["id"]))
    db.commit()

    assert db.query(Activity).count() == 0
