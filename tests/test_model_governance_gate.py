from __future__ import annotations

import json

from scripts.check_model_deployment_gate import main


def test_model_deployment_gate_passes_with_valid_candidate(tmp_path, monkeypatch) -> None:
    candidate = {
        "register_ready": True,
        "candidate": {
            "production_gate": {"passed": True},
            "test_metrics": {
                "precision": 0.75,
                "recall": 0.72,
                "pr_auc": 0.8,
                "false_alarm_frequency_per_day": 1.0,
                "business_net_value": 100.0,
            },
        },
    }
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_model_deployment_gate.py",
            "--candidate-json",
            str(path),
        ],
    )
    main()


def test_model_deployment_gate_fails_when_gate_false(tmp_path, monkeypatch) -> None:
    candidate = {
        "register_ready": False,
        "candidate": {
            "production_gate": {"passed": False},
            "test_metrics": {
                "precision": 0.5,
                "recall": 0.5,
                "pr_auc": 0.5,
                "false_alarm_frequency_per_day": 5.0,
                "business_net_value": -1.0,
            },
        },
    }
    path = tmp_path / "candidate_bad.json"
    path.write_text(json.dumps(candidate), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_model_deployment_gate.py",
            "--candidate-json",
            str(path),
        ],
    )

    try:
        main()
    except SystemExit as exc:
        assert "failed" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for failed gate")
