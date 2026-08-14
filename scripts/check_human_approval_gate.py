from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approval-file",
        default="governance/production_approval_record.json",
    )
    args = parser.parse_args()

    approval_path = Path(args.approval_file)
    if not approval_path.exists():
        raise SystemExit(f"Approval file not found: {approval_path}")

    payload = json.loads(approval_path.read_text(encoding="utf-8"))
    required = ["approved", "approved_by", "approved_at", "change_ticket", "scope"]
    missing = [field for field in required if field not in payload]

    for field in ["approved_by", "approved_at", "change_ticket", "scope"]:
        if field in payload and not payload.get(field):
            missing.append(field)

    if missing:
        raise SystemExit(f"Approval gate missing required fields: {missing}")

    if payload.get("approved") is not True:
        raise SystemExit("Production approval gate not satisfied: approved must be true")

    print(json.dumps({"status": "passed", "approver": payload.get("approved_by")}, indent=2))


if __name__ == "__main__":
    main()
