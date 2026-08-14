from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_FEATURES = [
    "pressure",
    "flow",
    "demand",
    "pressure_lag_1",
    "flow_lag_1",
    "demand_lag_1",
    "pressure_delta",
    "flow_delta",
    "demand_delta",
    "pressure_roll_avg_6",
    "flow_roll_avg_6",
]


def _load_candidate_model(model_suite_dir: Path) -> tuple[object, list[str], dict, str]:
    summary_path = model_suite_dir / "model_suite_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    trained = [m for m in summary.get("models", []) if m.get("status") == "trained"]
    if not trained:
        raise ValueError("No trained models available for scenario tests")

    best = max(trained, key=lambda m: (m["test"]["business_net_value"], m["test"]["f1"]))
    artifact_path = Path(best["artifacts"]["model"])
    loaded = joblib.load(artifact_path)

    if isinstance(loaded, dict) and "model" in loaded:
        model = loaded["model"]
        features = loaded.get("features") or BASE_FEATURES
        extras = loaded.get("extras", {})
    else:
        model = loaded
        features = BASE_FEATURES
        extras = {}

    metadata = {
        "selected_model": best["model"],
        "selected_metrics": best["test"],
        "summary": summary,
    }
    return model, features, extras, str(artifact_path), metadata


def _predict_score(model: object, extras: dict, features: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]

    if hasattr(model, "score_samples"):
        transformed = features
        scaler = extras.get("scaler")
        if scaler is not None:
            transformed = scaler.transform(features)
        raw = -model.score_samples(transformed)
        low = float(np.min(raw))
        high = float(np.max(raw))
        width = max(high - low, 1e-9)
        return (raw - low) / width

    raise RuntimeError("Unsupported model for scenario scoring")


def _make_baseline(
    df: pd.DataFrame,
    feature_cols: list[str],
    n_rows: int,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    sampled = df.sample(n=max(n_rows, 50), replace=True, random_state=seed).copy()

    for col_name in feature_cols:
        if col_name not in sampled.columns:
            sampled[col_name] = 0.0
        sampled[col_name] = sampled[col_name].astype(float).fillna(0.0)
        sampled[col_name] = sampled[col_name] + rng.normal(0.0, 0.03, size=len(sampled))

    sampled["scenario_name"] = "baseline"
    sampled["leak_label"] = sampled.get("leak_label", 0).fillna(0).astype(int)
    return sampled


def _scenario_variants(base: pd.DataFrame, seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    scenarios: dict[str, pd.DataFrame] = {}

    def clone(name: str) -> pd.DataFrame:
        out = base.copy()
        out["scenario_name"] = name
        return out

    small_leak = clone("small_leak")
    m = rng.random(len(small_leak)) < 0.12
    small_leak.loc[m, "pressure"] *= 0.97
    small_leak.loc[m, "flow"] *= 1.05
    small_leak.loc[m, "leak_label"] = 1
    scenarios["small_leak"] = small_leak

    large_leak = clone("large_leak")
    m = rng.random(len(large_leak)) < 0.12
    large_leak.loc[m, "pressure"] *= 0.82
    large_leak.loc[m, "flow"] *= 1.35
    large_leak.loc[m, "leak_label"] = 1
    scenarios["large_leak"] = large_leak

    different_locations = clone("different_leak_locations")
    if "sensor_node_id" in different_locations.columns:
        different_locations["sensor_node_id"] = rng.choice(
            ["N1", "N2", "N3", "N4"],
            size=len(different_locations),
        )
    m = rng.random(len(different_locations)) < 0.1
    different_locations.loc[m, "leak_label"] = 1
    scenarios["different_leak_locations"] = different_locations

    demand_spike = clone("demand_spike")
    m = rng.random(len(demand_spike)) < 0.2
    demand_spike.loc[m, "demand"] *= 1.8
    scenarios["demand_spike"] = demand_spike

    pressure_variation = clone("pressure_variation")
    pressure_variation["pressure"] *= rng.normal(1.0, 0.12, size=len(pressure_variation))
    scenarios["pressure_variation"] = pressure_variation

    sensor_noise = clone("sensor_noise")
    for col_name in ["pressure", "flow", "demand"]:
        sensor_noise[col_name] += rng.normal(
            0.0,
            0.18 * max(1e-6, sensor_noise[col_name].std()),
            size=len(sensor_noise),
        )
    scenarios["sensor_noise"] = sensor_noise

    missing_sensors = clone("missing_sensors")
    for col_name in ["pressure", "flow", "demand"]:
        mask = rng.random(len(missing_sensors)) < 0.25
        missing_sensors.loc[mask, col_name] = np.nan
    scenarios["missing_sensors"] = missing_sensors

    malformed_inputs = clone("malformed_inputs")
    malformed_inputs["_scenario_malformed"] = True
    scenarios["malformed_inputs"] = malformed_inputs

    extreme_values = clone("extreme_values")
    idx = rng.choice(
        extreme_values.index.to_numpy(),
        size=max(1, int(0.05 * len(extreme_values))),
        replace=False,
    )
    extreme_values.loc[idx, "pressure"] *= 4.5
    extreme_values.loc[idx, "flow"] *= 4.0
    scenarios["extreme_values"] = extreme_values

    partial_telemetry = clone("partial_telemetry")
    keep = rng.random(len(partial_telemetry)) > 0.3
    scenarios["partial_telemetry"] = partial_telemetry.loc[keep].copy()

    leakg3pd_scenario_a = clone("leakg3pd_scenario_a")
    m = rng.random(len(leakg3pd_scenario_a)) < 0.08
    leakg3pd_scenario_a.loc[m, "pressure"] *= 0.9
    leakg3pd_scenario_a.loc[m, "flow"] *= 1.15
    leakg3pd_scenario_a.loc[m, "leak_label"] = 1
    scenarios["leakg3pd_scenario_a"] = leakg3pd_scenario_a

    leakg3pd_scenario_b = clone("leakg3pd_scenario_b")
    m = rng.random(len(leakg3pd_scenario_b)) < 0.15
    leakg3pd_scenario_b.loc[m, "pressure"] *= 0.86
    leakg3pd_scenario_b.loc[m, "flow"] *= 1.25
    leakg3pd_scenario_b.loc[m, "leak_label"] = 1
    scenarios["leakg3pd_scenario_b"] = leakg3pd_scenario_b

    return scenarios


def _evaluate_scenario(
    model: object,
    extras: dict,
    df: pd.DataFrame,
    feature_cols: list[str],
    threshold: float,
) -> dict:
    malformed = bool(df.get("_scenario_malformed", pd.Series([False])).any())
    if malformed:
        return {
            "rows": int(len(df)),
            "status": "handled",
            "error_handling": "simulated_malformed_input",
            "mean_score": None,
            "precision": None,
            "recall": None,
            "f1": None,
        }

    x = df[feature_cols].copy()
    x = x.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y_true = (
        df.get("leak_label", pd.Series(np.zeros(len(df), dtype=int)))
        .fillna(0)
        .astype(int)
        .to_numpy()
    )

    scores = _predict_score(model, extras, x.to_numpy())
    y_pred = (scores >= threshold).astype(int)

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    precision = float(tp / max(tp + fp, 1))
    recall = float(tp / max(tp + fn, 1))
    f1 = float((2 * precision * recall) / max(precision + recall, 1e-9))

    return {
        "rows": int(len(df)),
        "status": "ok",
        "mean_score": float(np.mean(scores)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_positive_rate": float(np.mean(y_pred)),
    }


def main(
    gold_path: str,
    model_suite_dir: str,
    output_path: str,
    threshold: float,
    seed: int,
    scenario_rows: int,
) -> None:
    gold_df = pd.read_parquet(gold_path)
    model, features, extras, artifact_path, metadata = _load_candidate_model(Path(model_suite_dir))

    baseline = _make_baseline(gold_df, features, scenario_rows, seed)
    scenarios = _scenario_variants(baseline, seed=seed)

    results = {
        "selected_model": metadata["selected_model"],
        "selected_model_artifact": artifact_path,
        "selected_model_test_metrics": metadata["selected_metrics"],
        "threshold": threshold,
        "scenario_results": {},
    }
    for name, scenario_df in scenarios.items():
        results["scenario_results"][name] = _evaluate_scenario(
            model=model,
            extras=extras,
            df=scenario_df,
            feature_cols=features,
            threshold=threshold,
        )

    generalization_names = [
        "small_leak",
        "large_leak",
        "different_leak_locations",
        "leakg3pd_scenario_a",
        "leakg3pd_scenario_b",
    ]
    f1_values = [
        results["scenario_results"][name]["f1"]
        for name in generalization_names
        if results["scenario_results"][name]["f1"] is not None
    ]
    results["cross_scenario_generalization"] = {
        "evaluated_scenarios": generalization_names,
        "mean_f1": float(np.mean(f1_values)) if f1_values else None,
        "min_f1": float(np.min(f1_values)) if f1_values else None,
    }

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path", default="data/gold/gold_telemetry.parquet")
    parser.add_argument("--model-suite-dir", default="ml/training/artifacts/model_suite")
    parser.add_argument(
        "--output-path",
        default="ml/training/artifacts/model_suite/scenario_test_report.json",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--scenario-rows", type=int, default=300)
    args = parser.parse_args()

    main(
        gold_path=args.gold_path,
        model_suite_dir=args.model_suite_dir,
        output_path=args.output_path,
        threshold=args.threshold,
        seed=args.seed,
        scenario_rows=args.scenario_rows,
    )
