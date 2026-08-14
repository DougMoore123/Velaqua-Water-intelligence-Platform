from services.rag_service.app.main import EvidenceRequest, build_fallback_evidence


def test_fallback_evidence() -> None:
    req = EvidenceRequest(
        incident_id="INC-42",
        risk_score=0.83,
        recommended_action="dispatch_field_team",
        asset_ids=["PIPE-001"],
    )
    evidence = build_fallback_evidence(req)
    assert len(evidence.sources) >= 1
    assert len(evidence.citations) >= 1
    assert "INC-42" in evidence.rationale
