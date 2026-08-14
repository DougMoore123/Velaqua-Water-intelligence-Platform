from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from services.decision_api.app.decision_engine import compute_decision
from services.shared.models import (
    ApprovalRequest,
    ApprovalResponse,
    DecisionResponse,
    EvidencePackage,
    IntegrationDispatchResult,
    PredictionRequest,
)

app = FastAPI(title="Water Decision Intelligence API", version="0.1.0")

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001")
RAG_TIMEOUT_SECONDS = float(os.getenv("RAG_TIMEOUT_SECONDS", "8"))
RAG_MAX_RETRIES = int(os.getenv("RAG_MAX_RETRIES", "1"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "60"))
INTEGRATION_TIMEOUT_SECONDS = float(os.getenv("INTEGRATION_TIMEOUT_SECONDS", "4"))
OPS_DASHBOARD_URL = os.getenv("OPS_DASHBOARD_URL", "")
CMMS_WORK_ORDER_URL = os.getenv("CMMS_WORK_ORDER_URL", "")
FIELD_WORKFLOW_URL = os.getenv("FIELD_WORKFLOW_URL", "")
CUSTOMER_SERVICE_WORKFLOW_URL = os.getenv("CUSTOMER_SERVICE_WORKFLOW_URL", "")
EXECUTIVE_KPI_URL = os.getenv("EXECUTIVE_KPI_URL", "")

REQUEST_LOG: dict[str, deque[float]] = defaultdict(deque)
REQUEST_LOG_LOCK = Lock()
APPROVALS: dict[str, ApprovalResponse] = {}
INCIDENT_OUTCOMES: list[dict[str, Any]] = []


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _is_rate_limited(client_id: str) -> bool:
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with REQUEST_LOG_LOCK:
        log = REQUEST_LOG[client_id]
        while log and log[0] < cutoff:
            log.popleft()
        if len(log) >= RATE_LIMIT_MAX_REQUESTS:
            return True
        log.append(now)
    return False


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id", str(uuid4()))
    client_id = request.client.host if request.client else "unknown"

    if request.url.path not in {"/health", "/ready"} and _is_rate_limited(client_id):
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": "Too many requests. Retry later.",
                "request_id": _request_id(request),
            },
        )

    response = await call_next(request)
    response.headers["x-request-id"] = _request_id(request)
    return response


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "request_id": _request_id(request),
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "request_id": _request_id(request),
            "message": str(exc),
        },
    )


async def _fetch_evidence(evidence_payload: Dict[str, Any]) -> dict[str, Any] | None:
    for attempt in range(RAG_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=RAG_TIMEOUT_SECONDS) as client:
                resp = await client.post(f"{RAG_SERVICE_URL}/evidence", json=evidence_payload)
            if resp.status_code == 200:
                return resp.json()
        except httpx.HTTPError:
            pass
        if attempt < RAG_MAX_RETRIES:
            continue
    return None


def _integration_targets() -> dict[str, str]:
    return {
        "operations_dashboard": OPS_DASHBOARD_URL,
        "cmms_work_management": CMMS_WORK_ORDER_URL,
        "field_workflow": FIELD_WORKFLOW_URL,
        "customer_service_workflow": CUSTOMER_SERVICE_WORKFLOW_URL,
        "executive_kpi_reporting": EXECUTIVE_KPI_URL,
    }


async def _dispatch_integrations(payload: dict[str, Any]) -> list[IntegrationDispatchResult]:
    targets = _integration_targets()
    results: list[IntegrationDispatchResult] = []
    async with httpx.AsyncClient(timeout=INTEGRATION_TIMEOUT_SECONDS) as client:
        for target, url in targets.items():
            if not url:
                results.append(IntegrationDispatchResult(target=target, status="skipped"))
                continue
            try:
                resp = await client.post(url, json=payload)
                if 200 <= resp.status_code < 300:
                    results.append(
                        IntegrationDispatchResult(
                            target=target,
                            status="sent",
                            detail=f"http_{resp.status_code}",
                        )
                    )
                else:
                    results.append(
                        IntegrationDispatchResult(
                            target=target,
                            status="failed",
                            detail=f"http_{resp.status_code}",
                        )
                    )
            except httpx.HTTPError as exc:
                results.append(
                    IntegrationDispatchResult(target=target, status="failed", detail=str(exc))
                )
    return results


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> Dict[str, Any]:
    rag_configured = bool(RAG_SERVICE_URL)
    status = "ready" if rag_configured else "degraded"
    return {
        "status": status,
        "rag_service_url": RAG_SERVICE_URL,
        "rag_configured": rag_configured,
        "integrations_configured": {
            name: bool(url) for name, url in _integration_targets().items()
        },
    }


@app.post("/predict", response_model=DecisionResponse)
async def predict(payload: PredictionRequest) -> DecisionResponse:
    decision = compute_decision(payload)

    evidence_payload: Dict[str, Any] = {
        "incident_id": payload.incident_id,
        "risk_score": decision.risk_score,
        "recommended_action": decision.recommended_action,
        "asset_ids": list({t.asset_id for t in payload.telemetry}),
    }

    evidence = await _fetch_evidence(evidence_payload)
    if evidence:
        decision.evidence = EvidencePackage.model_validate(evidence)

    return decision


@app.post("/incident")
async def incident(payload: PredictionRequest) -> Dict[str, Any]:
    decision = await predict(payload)
    if not decision:
        raise HTTPException(status_code=500, detail="Decision generation failed")

    approval = APPROVALS.get(payload.incident_id)
    blocked = decision.material_field_action and (
        decision.requires_human_approval and (approval is None or not approval.approved)
    )

    if blocked:
        return {
            "incident_id": payload.incident_id,
            "status": "pending_authorization",
            "decision": decision,
            "material_action_executed": False,
            "approval_required": True,
            "approval": approval,
            "integration_dispatch": [],
        }

    integration_payload: dict[str, Any] = {
        "incident_id": payload.incident_id,
        "decision": decision.model_dump(),
        "approval": approval.model_dump() if approval else None,
    }
    integration_dispatch = await _dispatch_integrations(integration_payload)

    INCIDENT_OUTCOMES.append(
        {
            "incident_id": payload.incident_id,
            "risk_tier": decision.risk_tier,
            "material_field_action": decision.material_field_action,
            "recommended_action": decision.recommended_action,
            "approved": bool(approval.approved) if approval else False,
        }
    )

    return {
        "incident_id": payload.incident_id,
        "status": "authorized" if decision.material_field_action else "monitor_only",
        "decision": decision,
        "material_action_executed": bool(decision.material_field_action),
        "approval_required": bool(decision.requires_human_approval),
        "approval": approval,
        "integration_dispatch": [entry.model_dump() for entry in integration_dispatch],
    }


@app.post("/incident/approval", response_model=ApprovalResponse)
def incident_approval(payload: ApprovalRequest, response: Response) -> ApprovalResponse:
    status = "approved" if payload.approve else "rejected"
    approval = ApprovalResponse(
        incident_id=payload.incident_id,
        approved=payload.approve,
        approved_by=payload.approver_id,
        status=status,
        notes=payload.notes,
    )
    APPROVALS[payload.incident_id] = approval
    response.status_code = 202
    return approval


@app.get("/kpi/executive")
def executive_kpi() -> dict[str, Any]:
    total = len(INCIDENT_OUTCOMES)
    if total == 0:
        return {
            "total_incidents": 0,
            "material_actions": 0,
            "approval_rate": 0.0,
            "risk_tier_distribution": {"high": 0, "medium": 0, "low": 0},
        }

    material_actions = sum(1 for item in INCIDENT_OUTCOMES if item["material_field_action"])
    approved = sum(1 for item in INCIDENT_OUTCOMES if item["approved"])
    risk_tier_distribution = {
        "high": sum(1 for item in INCIDENT_OUTCOMES if item["risk_tier"] == "high"),
        "medium": sum(1 for item in INCIDENT_OUTCOMES if item["risk_tier"] == "medium"),
        "low": sum(1 for item in INCIDENT_OUTCOMES if item["risk_tier"] == "low"),
    }

    return {
        "total_incidents": total,
        "material_actions": material_actions,
        "approval_rate": round(approved / total, 4),
        "risk_tier_distribution": risk_tier_distribution,
    }
