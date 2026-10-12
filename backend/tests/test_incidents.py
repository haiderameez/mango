import pytest

from tests.conftest import auth_headers


def create_incident(client, headers, **overrides):
    payload = {"title": "Checkout 500s", "description": "db errors", "severity": "HIGH"}
    payload.update(overrides)

    response = client.post("/incidents", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def user_id(client, headers):
    return client.get("/auth/me", headers=headers).json()["id"]


def test_create_incident_defaults_to_open_and_unassigned(client, headers):
    body = create_incident(client, headers)

    assert body["status"] == "OPEN"
    assert body["assigned_to"] is None
    assert body["created_by"] == user_id(client, headers)


def test_create_incident_requires_authentication(client):
    response = client.post("/incidents", json={"title": "x", "severity": "LOW"})

    assert response.status_code == 401


def test_create_incident_rejects_empty_title(client, headers):
    response = client.post("/incidents", json={"title": "", "severity": "LOW"}, headers=headers)

    assert response.status_code == 422


def test_create_incident_rejects_unknown_severity(client, headers):
    response = client.post("/incidents", json={"title": "x", "severity": "SPICY"}, headers=headers)

    assert response.status_code == 422


def test_get_incident_by_id(client, headers):
    created = create_incident(client, headers)

    response = client.get(f"/incidents/{created['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_incident_returns_404(client, headers):
    assert client.get("/incidents/404", headers=headers).status_code == 404


def test_list_incidents_is_newest_first(client, headers):
    first = create_incident(client, headers, title="first")
    second = create_incident(client, headers, title="second")

    body = client.get("/incidents", headers=headers).json()

    assert [i["id"] for i in body] == [second["id"], first["id"]]


def test_assign_incident_as_creator(client, headers, other_headers):
    created = create_incident(client, headers)
    target = user_id(client, other_headers)

    response = client.patch(
        f"/incidents/{created['id']}/assign", json={"assigned_to": target}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["assigned_to"] == target


def test_assignee_cannot_reassign(client, headers, other_headers):
    created = create_incident(client, headers)
    target = user_id(client, other_headers)
    client.patch(
        f"/incidents/{created['id']}/assign", json={"assigned_to": target}, headers=headers
    )

    response = client.patch(
        f"/incidents/{created['id']}/assign", json={"assigned_to": target}, headers=other_headers
    )

    assert response.status_code == 403


def test_assign_to_unknown_user_returns_404(client, headers):
    created = create_incident(client, headers)

    response = client.patch(
        f"/incidents/{created['id']}/assign", json={"assigned_to": 9999}, headers=headers
    )

    assert response.status_code == 404


def test_resolved_incident_cannot_be_assigned(client, headers, other_headers):
    created = create_incident(client, headers)
    client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )
    client.patch(f"/incidents/{created['id']}/status", json={"status": "RESOLVED"}, headers=headers)

    response = client.patch(
        f"/incidents/{created['id']}/assign",
        json={"assigned_to": user_id(client, other_headers)},
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.parametrize("target", ["RESOLVED", "OPEN"])
def test_open_incident_can_only_move_to_investigating(client, headers, target):
    created = create_incident(client, headers)

    response = client.patch(
        f"/incidents/{created['id']}/status", json={"status": target}, headers=headers
    )

    assert response.status_code == 403


def test_full_status_lifecycle(client, headers):
    created = create_incident(client, headers)

    investigating = client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )
    resolved = client.patch(
        f"/incidents/{created['id']}/status", json={"status": "RESOLVED"}, headers=headers
    )

    assert investigating.json()["status"] == "INVESTIGATING"
    assert resolved.json()["status"] == "RESOLVED"


def test_resolved_incident_cannot_change_status(client, headers):
    created = create_incident(client, headers)
    client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )
    client.patch(f"/incidents/{created['id']}/status", json={"status": "RESOLVED"}, headers=headers)

    response = client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    assert response.status_code == 403


def test_investigating_cannot_go_back_to_open(client, headers):
    created = create_incident(client, headers)
    client.patch(
        f"/incidents/{created['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    response = client.patch(
        f"/incidents/{created['id']}/status", json={"status": "OPEN"}, headers=headers
    )

    assert response.status_code == 403


def test_unrelated_user_cannot_change_status(client, headers, other_headers):
    created = create_incident(client, headers)

    response = client.patch(
        f"/incidents/{created['id']}/status",
        json={"status": "INVESTIGATING"},
        headers=other_headers,
    )

    assert response.status_code == 403


def test_assignee_can_change_status(client, headers, other_headers):
    created = create_incident(client, headers)
    client.patch(
        f"/incidents/{created['id']}/assign",
        json={"assigned_to": user_id(client, other_headers)},
        headers=headers,
    )

    response = client.patch(
        f"/incidents/{created['id']}/status",
        json={"status": "INVESTIGATING"},
        headers=other_headers,
    )

    assert response.status_code == 200


def test_status_change_on_missing_incident_returns_404(client, headers):
    response = client.patch(
        "/incidents/404/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    assert response.status_code == 404


# --- filtering and pagination ---------------------------------------------------------


def test_filter_by_status(client, headers):
    create_incident(client, headers, title="stays open")
    moving = create_incident(client, headers, title="moving")
    client.patch(
        f"/incidents/{moving['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )

    body = client.get("/incidents?status=INVESTIGATING", headers=headers).json()

    assert [i["id"] for i in body] == [moving["id"]]


def test_filter_by_severity(client, headers):
    create_incident(client, headers, severity="LOW")
    critical = create_incident(client, headers, severity="CRITICAL")

    body = client.get("/incidents?severity=CRITICAL", headers=headers).json()

    assert [i["id"] for i in body] == [critical["id"]]


def test_filter_by_assignee_and_severity_together(client, headers, other_headers):
    target = user_id(client, other_headers)
    create_incident(client, headers, severity="CRITICAL", title="critical unassigned")
    assigned_low = create_incident(client, headers, severity="LOW", title="low assigned")
    assigned_critical = create_incident(client, headers, severity="CRITICAL", title="both")

    for incident in (assigned_low, assigned_critical):
        client.patch(
            f"/incidents/{incident['id']}/assign",
            json={"assigned_to": target},
            headers=headers,
        )

    body = client.get(
        f"/incidents?severity=CRITICAL&assigned_to={target}", headers=headers
    ).json()

    assert [i["id"] for i in body] == [assigned_critical["id"]]


def test_filter_by_creator(client, headers, other_headers):
    mine = create_incident(client, headers)
    create_incident(client, other_headers, title="theirs")

    body = client.get(f"/incidents?created_by={user_id(client, headers)}", headers=headers).json()

    assert [i["id"] for i in body] == [mine["id"]]


def test_search_matches_title_case_insensitively(client, headers):
    match = create_incident(client, headers, title="Payment gateway timeout")
    create_incident(client, headers, title="Disk pressure")

    body = client.get("/incidents?search=GATEWAY", headers=headers).json()

    assert [i["id"] for i in body] == [match["id"]]


def test_pagination_limit_and_offset(client, headers):
    created = [create_incident(client, headers, title=f"i{n}") for n in range(5)]
    newest_first = [i["id"] for i in reversed(created)]

    page_one = client.get("/incidents?limit=2", headers=headers).json()
    page_two = client.get("/incidents?limit=2&offset=2", headers=headers).json()

    assert [i["id"] for i in page_one] == newest_first[:2]
    assert [i["id"] for i in page_two] == newest_first[2:4]


def test_default_page_size_is_capped(client, headers):
    assert client.get("/incidents?limit=0", headers=headers).status_code == 422
    assert client.get("/incidents?limit=101", headers=headers).status_code == 422


def test_filters_do_not_leak_across_users(client, headers):
    """Filtering is a view over all incidents: Mango is a team tool, not per-user silos."""
    create_incident(client, headers)
    foreign = auth_headers(client, email="third@example.com", name="Third")

    assert len(client.get("/incidents", headers=foreign).json()) == 1
