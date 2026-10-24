def test_metrics_endpoint_exposes_http_request_metrics(client):
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "mango_http_requests_total" in response.text
    assert 'route="/health"' in response.text
