from __future__ import annotations

from fastapi.testclient import TestClient

from services.decision_api.app.main import app

client = TestClient(app)


def test_ready_endpoint_reports_integration_configuration() -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "integrations_configured" in body


def test_kpi_endpoint_returns_shape() -> None:
    response = client.get("/kpi/executive")
    assert response.status_code == 200
    body = response.json()
    assert "total_incidents" in body
    assert "risk_tier_distribution" in body
