def test_health_check(client_no_db):
    """Test health check endpoint returns ok status."""
    response = client_no_db.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client_no_db):
    """Test root endpoint returns app info."""
    response = client_no_db.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data
    assert data["version"] == "1.0.0"
