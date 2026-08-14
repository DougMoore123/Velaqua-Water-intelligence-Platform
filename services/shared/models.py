from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TelemetryPoint(BaseModel):
    timestamp: datetime
    asset_id: str
    node_id: str
    pressure: float
    flow: float
    demand: float


class PredictionRequest(BaseModel):
    incident_id: str
    telemetry: List[TelemetryPoint]
    anomaly_score: float = Field(ge=0.0, le=1.0)
    leak_probability: float = Field(ge=0.0, le=1.0)
    forecast_stress_index: float = Field(ge=0.0, le=1.0)


class EvidencePackage(BaseModel):
    sources: List[str]
    rationale: str
    suggested_response: str
    citations: List[str] = []


class DecisionContext(BaseModel):
    asset_ids: List[str]
    telemetry_points: int
    max_pressure: float
    max_flow: float
    avg_demand: float


class DecisionResponse(BaseModel):
    incident_id: str
    risk_score: float
    risk_tier: str
    confidence: float
    recommended_action: str
    material_field_action: bool
    requires_human_approval: bool
    approval_reason: Optional[str] = None
    context: DecisionContext
    evidence: Optional[EvidencePackage] = None


class ApprovalRequest(BaseModel):
    incident_id: str
    approver_id: str
    approve: bool
    notes: Optional[str] = None


class ApprovalResponse(BaseModel):
    incident_id: str
    approved: bool
    approved_by: str
    status: str
    notes: Optional[str] = None


class IntegrationDispatchResult(BaseModel):
    target: str
    status: str
    detail: Optional[str] = None
