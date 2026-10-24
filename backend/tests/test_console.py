"""The console is a static page with no privileged path into the API."""


def test_console_page_is_served(client):
    response = client.get("/console")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Mango" in response.text


def test_console_page_needs_no_token(client):
    """The page itself is public; everything it fetches is not."""
    assert client.get("/console").status_code == 200


def test_there_is_no_console_back_door(client):
    """The development sign-in seam is gone: the console authenticates like any client."""
    assert client.get("/console/token").status_code == 404


def test_the_page_signs_in_through_the_ordinary_auth_endpoints(client):
    page = client.get("/console").text

    assert "/auth/login" in page
    assert "/auth/register" in page
    assert "/auth/me" in page


def test_console_has_clearable_search_and_a_multiline_case_description(client):
    page = client.get("/console").text

    assert 'aria-label="Clear case title search"' in page
    assert 'id="q-clear"' in page
    assert '<textarea class="inp" id="n-desc"' in page


def test_every_data_endpoint_the_console_uses_rejects_an_anonymous_caller(client, headers):
    created = client.post(
        "/incidents", json={"title": "x", "severity": "LOW"}, headers=headers
    ).json()

    for method, path in [
        ("get", "/incidents"),
        ("get", f"/incidents/{created['id']}"),
        ("get", f"/incidents/{created['id']}/activity"),
        ("get", f"/incidents/{created['id']}/comments"),
        ("get", f"/incidents/{created['id']}/investigation"),
        ("get", "/investigations/quota"),
        ("get", "/auth/me"),
        ("post", f"/incidents/{created['id']}/investigate"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, f"{method.upper()} {path} allowed an anonymous caller"
