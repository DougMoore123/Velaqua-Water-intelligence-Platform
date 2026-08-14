from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_e2e_pipeline_chain_script_contains_required_steps() -> None:
    script = _read("scripts/run_e2e_pipeline_v1.sh")
    assert "check_model_deployment_gate.py" in script
    assert "register_production_candidate.sh" in script
    assert "deploy_realtime_endpoint_v1.sh" in script
    assert "smoke_test_realtime_endpoint_v1.sh" in script
    assert "check_human_approval_gate.py" in script


def test_release_gate_script_runs_steps_4_to_8() -> None:
    script = _read("scripts/run_release_gate_steps_4_8.sh")
    assert "blue_green_compare_v1.sh" in script
    assert "promote_green_v1.sh" in script
    assert "load_test_endpoint.py" in script
    assert "rollback_to_blue_v1.sh" in script


def test_monitoring_security_orchestrator_runs_gate_flow() -> None:
    script = _read("scripts/run_monitoring_security_orchestrator.sh")
    assert "configure_monitoring_baseline.sh" in script
    assert "configure_security_governance_baseline.sh" in script
    assert "test_autoscaling_v1.sh" in script
    assert "monitor_operational_metrics.py" in script
    assert "evaluate_slo_gate.py" in script
