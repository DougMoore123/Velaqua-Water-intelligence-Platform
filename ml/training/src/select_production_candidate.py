from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        return _sha256_file(path)

    for file_path in sorted([p for p in path.rglob("*") if p.is_file()]):
        rel = str(file_path.relative_to(path)).encode("utf-8")
        digest.update(rel)
        digest.update(_sha256_file(file_path).encode("utf-8"))
    return digest.hexdigest()


def _git_sha(repo_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return "unknown_not_git_repo"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pick_candidate(model_summary: dict, scenario_report: dict) -> dict:
    trained = [m for m in model_summary.get("models", []) if m.get("status") == "trained"]
    if not trained:
        raise ValueError("No trained models available in model_suite_summary.json")

    scenario_generalization = scenario_report.get("cross_scenario_generalization", {})
    generalization_mean_f1 = scenario_generalization.get("mean_f1") or 0.0

    best = max(
        trained,
        key=lambda m: (
            m["test"]["business_net_value"],
            m["test"]["pr_auc"],
            m["test"]["f1"],
        ),
    )

    gate = model_summary.get("production_gate", {})
    return {
        "model_name": best["model"],
        "model_artifact": best["artifacts"]["model"],
        "test_metrics": best["test"],
        "val_metrics": best["val"],
        "scenario_generalization_mean_f1": generalization_mean_f1,
        "production_gate": gate,
        "data_sufficiency": model_summary.get("data_sufficiency", {}),
    }


def _write_rationale(path: Path, candidate: dict, lineage: dict) -> None:
    suff = candidate.get("data_sufficiency", {})
    lines = [
        "# Production Candidate Rationale",
        "",
        f"Selected model: {candidate['model_name']}",
        "",
        "## Why This Model",
        "- Highest business net value among trained candidates.",
        "- Competitive PR-AUC and F1 on holdout test split.",
        (
            "- Evaluated against stress scenarios for leak size, location, noise, "
            "and malformed input handling."
        ),
        "",
        "## Key Evaluation Results",
        f"- Test precision: {candidate['test_metrics']['precision']:.4f}",
        f"- Test recall: {candidate['test_metrics']['recall']:.4f}",
        f"- Test F1: {candidate['test_metrics']['f1']:.4f}",
        f"- Test PR-AUC: {candidate['test_metrics']['pr_auc']:.4f}",
        f"- Cross-scenario mean F1: {candidate['scenario_generalization_mean_f1']:.4f}",
        "",
        "## Lineage and Reproducibility",
        f"- Git commit SHA: {lineage['git_commit_sha']}",
        f"- Data version: {lineage['data_version']}",
        f"- Feature version: {lineage['feature_version']}",
        f"- Hyperparameter profile: {lineage['hyperparameters']}",
        "",
        "## Production Gate",
        f"- Gate passed: {candidate['production_gate'].get('passed', False)}",
        f"- Gate conditions: {candidate['production_gate'].get('conditions', {})}",
        "",
        "## Data Sufficiency",
        f"- Ready: {suff.get('ready', False)}",
        f"- Minimums: {suff.get('minimums', {})}",
        f"- Actuals: {suff.get('actuals', {})}",
        f"- Remaining gaps: {suff.get('gaps', {})}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(
    model_suite_dir: str,
    gold_path: str,
    feature_dict_path: str,
    output_json: str,
    output_md: str,
    repo_root: str,
) -> None:
    suite_dir = Path(model_suite_dir)
    model_summary = _load_json(suite_dir / "model_suite_summary.json")
    scenario_report = _load_json(suite_dir / "scenario_test_report.json")

    candidate = _pick_candidate(model_summary, scenario_report)

    lineage = {
        "git_commit_sha": _git_sha(Path(repo_root)),
        "data_version": _sha256_tree(Path(gold_path)),
        "feature_version": _sha256_tree(Path(feature_dict_path)),
        "hyperparameters": {
            "threshold_default": model_summary.get("models", [{}])[0].get("threshold_default", 0.5),
            "cost_missed_leak": model_summary.get("business_inputs", {}).get("cost_missed_leak"),
            "cost_false_alarm": model_summary.get("business_inputs", {}).get("cost_false_alarm"),
            "value_early_detection": model_summary.get("business_inputs", {}).get(
                "value_early_detection"
            ),
        },
        "evaluation_results_path": str(suite_dir / "model_suite_summary.json"),
        "scenario_results_path": str(suite_dir / "scenario_test_report.json"),
    }

    payload = {
        "candidate": candidate,
        "lineage": lineage,
        "register_ready": bool(candidate["production_gate"].get("passed", False)),
    }

    output_json_path = Path(output_json)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    output_md_path = Path(output_md)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    _write_rationale(output_md_path, candidate, lineage)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-suite-dir", default="ml/training/artifacts/model_suite")
    parser.add_argument("--gold-path", default="data/gold/gold_telemetry.parquet")
    parser.add_argument("--feature-dict-path", default="data/gold/feature_dictionary_json")
    parser.add_argument(
        "--output-json",
        default="ml/training/artifacts/model_suite/production_candidate.json",
    )
    parser.add_argument(
        "--output-md",
        default="ml/training/artifacts/model_suite/model_selection_rationale.md",
    )
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    main(
        model_suite_dir=args.model_suite_dir,
        gold_path=args.gold_path,
        feature_dict_path=args.feature_dict_path,
        output_json=args.output_json,
        output_md=args.output_md,
        repo_root=args.repo_root,
    )
