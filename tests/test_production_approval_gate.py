from __future__ import annotations

import json

from scripts.check_human_approval_gate import main


def test_human_approval_gate_passes(tmp_path, monkeypatch) -> None:
    payload = {
        "approved": True,
        "approved_by": "ops_manager",
        "approved_at": "2026-08-13T10:00:00Z",
        "change_ticket": "CHG-1234",
        "scope": "green promotion to production",
    }
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["check_human_approval_gate.py", "--approval-file", str(approval_file)],
    )
    main()


def test_human_approval_gate_fails_when_not_approved(tmp_path, monkeypatch) -> None:
    payload = {
        "approved": False,
        "approved_by": "ops_manager",
        "approved_at": "2026-08-13T10:00:00Z",
        "change_ticket": "CHG-1234",
        "scope": "green promotion to production",
    }
    approval_file = tmp_path / "approval.json"
    approval_file.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        ["check_human_approval_gate.py", "--approval-file", str(approval_file)],
    )

    try:
        main()
    except SystemExit as exc:
        assert "not satisfied" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for missing approval")
