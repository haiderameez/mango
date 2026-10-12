def post_comment(client, headers, incident_id, content="Looking into it"):
    return client.post(
        f"/incidents/{incident_id}/comments", json={"content": content}, headers=headers
    )


def test_any_authenticated_engineer_can_comment(client, incident, other_headers):
    response = post_comment(client, other_headers, incident["id"])

    assert response.status_code == 201
    assert response.json()["incident_id"] == incident["id"]


def test_comment_author_comes_from_the_token_not_the_body(client, incident, headers):
    me = client.get("/auth/me", headers=headers).json()["id"]

    response = client.post(
        f"/incidents/{incident['id']}/comments",
        json={"content": "hi", "user_id": 9999},
        headers=headers,
    )

    assert response.json()["user_id"] == me


def test_comment_requires_authentication(client, incident):
    response = client.post(
        f"/incidents/{incident['id']}/comments", json={"content": "anonymous"}
    )

    assert response.status_code == 401


def test_comment_on_missing_incident_returns_404(client, headers):
    assert post_comment(client, headers, 404).status_code == 404


def test_list_comments_for_incident(client, incident, headers, other_headers):
    post_comment(client, headers, incident["id"], "first")
    post_comment(client, other_headers, incident["id"], "second")

    body = client.get(f"/incidents/{incident['id']}/comments", headers=headers).json()

    assert [c["content"] for c in body] == ["first", "second"]


def test_list_comments_for_missing_incident_returns_404(client, headers):
    assert client.get("/incidents/404/comments", headers=headers).status_code == 404


def test_get_comment_by_id(client, incident, headers):
    created = post_comment(client, headers, incident["id"]).json()

    response = client.get(f"/comments/{created['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_comment_returns_404(client, headers):
    assert client.get("/comments/404", headers=headers).status_code == 404


def test_author_can_edit_their_comment(client, incident, headers):
    created = post_comment(client, headers, incident["id"]).json()

    response = client.patch(
        f"/comments/{created['id']}", json={"content": "edited"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["content"] == "edited"
    assert response.json()["updated_at"] >= created["updated_at"]


def test_other_user_cannot_edit_a_comment(client, incident, headers, other_headers):
    created = post_comment(client, headers, incident["id"]).json()

    response = client.patch(
        f"/comments/{created['id']}", json={"content": "hijacked"}, headers=other_headers
    )

    assert response.status_code == 403
    assert client.get(f"/comments/{created['id']}", headers=headers).json()["content"] != "hijacked"


def test_other_user_cannot_delete_a_comment(client, incident, headers, other_headers):
    created = post_comment(client, headers, incident["id"]).json()

    response = client.delete(f"/comments/{created['id']}", headers=other_headers)

    assert response.status_code == 403
    assert client.get(f"/comments/{created['id']}", headers=headers).status_code == 200


def test_author_can_delete_their_comment(client, incident, headers):
    created = post_comment(client, headers, incident["id"]).json()

    assert client.delete(f"/comments/{created['id']}", headers=headers).status_code == 204
    assert client.get(f"/comments/{created['id']}", headers=headers).status_code == 404


def test_deleting_a_missing_comment_returns_404(client, headers):
    assert client.delete("/comments/404", headers=headers).status_code == 404


def test_comments_are_allowed_on_resolved_incidents(client, incident, headers):
    client.patch(
        f"/incidents/{incident['id']}/status", json={"status": "INVESTIGATING"}, headers=headers
    )
    client.patch(
        f"/incidents/{incident['id']}/status", json={"status": "RESOLVED"}, headers=headers
    )

    assert post_comment(client, headers, incident["id"]).status_code == 201


def test_deleting_an_incident_cascades_to_its_comments(client, incident, headers, db):
    """Mango has no delete endpoint; this guards the FK that a future one would rely on."""
    from app.models.comment import Comment
    from app.models.incident import Incident

    post_comment(client, headers, incident["id"])

    db.delete(db.get(Incident, incident["id"]))
    db.commit()

    assert db.query(Comment).count() == 0
