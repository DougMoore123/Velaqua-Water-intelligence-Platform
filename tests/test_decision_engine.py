from datetime import datetime, timezone

from services.decision_api.app.decision_engine import compute_decision
from services.shared.models import PredictionRequest, TelemetryPoint


def _sample_request(leak_probability: float, anomaly_score: float) -> PredictionRequest:
    return PredictionRequest(
        incident_id="INC-1",
        telemetry=[
            TelemetryPoint(
                timestamp=datetime.now(timezone.utc),
                asset_id="PIPE-001",
                node_id="N-42",
                pressure=52.1,
                flow=12.7,
                demand=6.2,
            )
        ],
        anomaly_score=anomaly_score,
        leak_probability=leak_probability,
        forecast_stress_index=0.4,
    )


def test_high_risk_dispatch() -> None:
    response = compute_decision(_sample_request(leak_probability=0.95, anomaly_score=0.9))
    assert response.material_field_action is True
    assert response.recommended_action == "dispatch_field_team"


def test_low_risk_monitor() -> None:
    response = compute_decision(_sample_request(leak_probability=0.2, anomaly_score=0.1))
    assert response.material_field_action is False
    assert response.recommended_action == "monitor_and_notify"
