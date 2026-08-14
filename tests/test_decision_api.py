from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.decision_api.app import main as decision_main

client = TestClient(decision_main.app)


@pytest.fixture(autouse=True)
def _reset_globals() -> None:
    decision_main.REQUEST_LOG.clear()
    decision_main.APPROVALS.clear()
    decision_main.INCIDENT_OUTCOMES.clear()
    decision_main.RATE_LIMIT_MAX_REQUESTS = 60
    decision_main.RATE_LIMIT_WINDOW_SECONDS = 60


def _payload(anomaly_score: float = 0.72) -> dict:
    return {
        "incident_id": "INC-900",
        "telemetry": [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "asset_id": "PIPE-001",
                "node_id": "N-21",
                "pressure": 58.2,
                "flow": 11.4,
                "demand": 7.3,
            }
        ],
        "anomaly_score": anomaly_score,
        "leak_probability": 0.84,
        "forecast_stress_index": 0.66,
    }


def test_predict_includes_operational_fields(monkeypatch) -> None:
    async def _mock_evidence(_: dict):
        return {
            "sources": ["ops-guide"],
            "rationale": "Synthetic rationale",
            "suggested_response": "dispatch_field_team",
        }

    monkeypatch.setattr(decision_main, "_fetch_evidence", _mock_evidence)
    response = client.post("/predict", json=_payload())
    body = response.json()

    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert body["risk_tier"] in {"low", "medium", "high"}
    assert "requires_human_approval" in body
    assert "context" in body
    assert body["context"]["telemetry_points"] == 1
    assert body["evidence"]["sources"][0] == "ops-guide"


def test_rate_limit_returns_429() -> None:
    decision_main.RATE_LIMIT_MAX_REQUESTS = 1
    decision_main.RATE_LIMIT_WINDOW_SECONDS = 60

    first = client.post("/predict", json=_payload())
    second = client.post("/predict", json=_payload())

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limit_exceeded"


def test_validation_error_shape() -> None:
    response = client.post("/predict", json=_payload(anomaly_score=1.2))

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert "request_id" in response.json()


def test_incident_approval_endpoint() -> None:
    response = client.post(
        "/incident/approval",
        json={
            "incident_id": "INC-900",
            "approver_id": "operator-1",
            "approve": True,
            "notes": "Pressure trend confirms dispatch",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == "operator-1"


def test_incident_blocks_material_action_without_approval(monkeypatch) -> None:
    async def _mock_evidence(_: dict):
        return {
            "sources": ["ops-guide"],
            "rationale": "Grounded evidence",
            "suggested_response": "dispatch_field_team",
            "citations": ["sop::1::Leak SOP"],
        }

    monkeypatch.setattr(decision_main, "_fetch_evidence", _mock_evidence)
    response = client.post("/incident", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_authorization"
    assert body["material_action_executed"] is False
    assert body["approval_required"] is True


def test_incident_dispatches_integrations_after_approval(monkeypatch) -> None:
    async def _mock_evidence(_: dict):
        return {
            "sources": ["ops-guide"],
            "rationale": "Grounded evidence",
            "suggested_response": "dispatch_field_team",
            "citations": ["sop::1::Leak SOP"],
        }

    async def _mock_dispatch(_: dict):
        return [
            decision_main.IntegrationDispatchResult(
                target="operations_dashboard",
                status="sent",
                detail="http_200",
            )
        ]

    monkeypatch.setattr(decision_main, "_fetch_evidence", _mock_evidence)
    monkeypatch.setattr(decision_main, "_dispatch_integrations", _mock_dispatch)

    approve = client.post(
        "/incident/approval",
        json={
            "incident_id": "INC-900",
            "approver_id": "operator-1",
            "approve": True,
            "notes": "Approved for dispatch",
        },
    )
    assert approve.status_code == 202

    response = client.post("/incident", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "authorized"
    assert len(body["integration_dispatch"]) == 1
    assert body["integration_dispatch"][0]["target"] == "operations_dashboard"


def test_executive_kpi_endpoint(monkeypatch) -> None:
    async def _mock_evidence(_: dict):
        return {
            "sources": ["ops-guide"],
            "rationale": "Grounded evidence",
            "suggested_response": "dispatch_field_team",
            "citations": ["sop::1::Leak SOP"],
        }

    async def _mock_dispatch(_: dict):
        return []

    monkeypatch.setattr(decision_main, "_fetch_evidence", _mock_evidence)
    monkeypatch.setattr(decision_main, "_dispatch_integrations", _mock_dispatch)

    client.post(
        "/incident/approval",
        json={
            "incident_id": "INC-900",
            "approver_id": "operator-1",
            "approve": True,
        },
    )
    client.post("/incident", json=_payload())

    kpi = client.get("/kpi/executive")
    assert kpi.status_code == 200
    assert kpi.json()["total_incidents"] == 1
