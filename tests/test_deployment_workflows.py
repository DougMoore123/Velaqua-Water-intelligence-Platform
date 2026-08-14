from __future__ import annotations

from pathlib import Path


def test_deploy_workflow_uses_aml_v1_scripts() -> None:
    workflow = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")
    assert "deploy_realtime_endpoint_v1.sh" in workflow
    assert "deploy_green_candidate_v1.sh" in workflow
    assert "az ml online-endpoint" not in workflow


def test_repository_workflow_has_governance_checks() -> None:
    workflow = Path(".github/workflows/repository-workflow.yml").read_text(encoding="utf-8")
    assert "production_approval_record.json" in workflow
    assert "production_readiness_review.md" in workflow
