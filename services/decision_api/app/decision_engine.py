from __future__ import annotations

from services.shared.models import DecisionContext, DecisionResponse, PredictionRequest


def compute_decision(payload: PredictionRequest) -> DecisionResponse:
    asset_ids = sorted({item.asset_id for item in payload.telemetry})
    pressures = [item.pressure for item in payload.telemetry]
    flows = [item.flow for item in payload.telemetry]
    demands = [item.demand for item in payload.telemetry]

    risk_score = (
        0.45 * payload.leak_probability
        + 0.35 * payload.anomaly_score
        + 0.20 * payload.forecast_stress_index
    )

    confidence = min(0.99, max(payload.leak_probability, payload.anomaly_score))

    if risk_score >= 0.75:
        action = "dispatch_field_team"
        material = True
        risk_tier = "high"
    elif risk_score >= 0.50:
        action = "schedule_inspection"
        material = True
        risk_tier = "medium"
    else:
        action = "monitor_and_notify"
        material = False
        risk_tier = "low"

    requires_human_approval = bool(risk_score >= 0.5 or confidence < 0.6)
    approval_reason = None
    if requires_human_approval:
        approval_reason = "Material action or low-confidence scenario requires operator approval."

    return DecisionResponse(
        incident_id=payload.incident_id,
        risk_score=round(risk_score, 4),
        risk_tier=risk_tier,
        confidence=round(confidence, 4),
        recommended_action=action,
        material_field_action=material,
        requires_human_approval=requires_human_approval,
        approval_reason=approval_reason,
        context=DecisionContext(
            asset_ids=asset_ids,
            telemetry_points=len(payload.telemetry),
            max_pressure=round(max(pressures), 4),
            max_flow=round(max(flows), 4),
            avg_demand=round(sum(demands) / len(demands), 4),
        ),
    )
