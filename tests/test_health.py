"""Health check endpoint tests."""


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert "service" in data
