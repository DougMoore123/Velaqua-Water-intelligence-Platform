from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
except ImportError:  # pragma: no cover
    XGBClassifier = None

try:
    import mlflow
except ImportError:  # pragma: no cover
    mlflow = None


TARGET_COLUMN = "target_leak_horizon"
TIME_COLUMN = "event_ts_utc"
ID_COLUMNS = {
    "sensor_node_id",
    "_ingest_ts",
    "_source_file",
    "_source_type",
    "_row_hash",
    "pressure_unit",
    "flow_unit",
    "demand_unit",
    "pressure_unit_standard",
    "flow_unit_standard",
    "demand_unit_standard",
}


@dataclass
class SplitData:
    x_train: pd.DataFrame
    y_train: np.ndarray
    ts_train: pd.Series
    src_train: pd.Series
    x_val: pd.DataFrame
    y_val: np.ndarray
    ts_val: pd.Series
    src_val: pd.Series
    x_test: pd.DataFrame
    y_test: np.ndarray
    ts_test: pd.Series
    src_test: pd.Series


def _safe_pr_auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if int(np.sum(y_true)) == 0:
        return 0.0
    return float(average_precision_score(y_true, y_score))


def _candidate_features(df: pd.DataFrame) -> list[str]:
    excluded = ID_COLUMNS | {TIME_COLUMN, TARGET_COLUMN, "leak_label"}
    cols = [c for c in df.columns if c not in excluded]
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    return sorted(numeric)


def _check_leakage(features: list[str]) -> list[str]:
    flagged = []
    for name in features:
        lowered = name.lower()
        if "target" in lowered or "future" in lowered:
            flagged.append(name)
    return flagged


def _make_split_frames(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    feature_cols: list[str],
) -> SplitData:
    return SplitData(
        x_train=train_df[feature_cols].fillna(0),
        y_train=train_df[TARGET_COLUMN].astype(int).to_numpy(),
        ts_train=train_df[TIME_COLUMN],
        src_train=train_df["_source_type"],
        x_val=val_df[feature_cols].fillna(0),
        y_val=val_df[TARGET_COLUMN].astype(int).to_numpy(),
        ts_val=val_df[TIME_COLUMN],
        src_val=val_df["_source_type"],
        x_test=test_df[feature_cols].fillna(0),
        y_test=test_df[TARGET_COLUMN].astype(int).to_numpy(),
        ts_test=test_df[TIME_COLUMN],
        src_test=test_df["_source_type"],
    )


def _temporal_split(
    df: pd.DataFrame,
    train_frac: float,
    val_frac: float,
    enforce_real_holdout: bool,
    feature_cols: list[str],
) -> tuple[SplitData, dict]:
    ordered = df.sort_values(TIME_COLUMN).reset_index(drop=True)
    n = len(ordered)
    if n < 5:
        raise ValueError("Need at least 5 rows for temporal train/val/test split")

    policy = "temporal_all"
    if enforce_real_holdout:
        real_df = ordered[ordered["_source_type"] == "real"].copy()
        synth_df = ordered[ordered["_source_type"] != "real"].copy()
        if len(real_df) >= 5:
            train_end_real = max(2, int(len(real_df) * train_frac))
            val_end_real = max(train_end_real + 1, int(len(real_df) * (train_frac + val_frac)))
            val_end_real = min(val_end_real, len(real_df) - 1)

            real_train = real_df.iloc[:train_end_real].copy()
            real_val = real_df.iloc[train_end_real:val_end_real].copy()
            real_test = real_df.iloc[val_end_real:].copy()
            if len(real_val) >= 1 and len(real_test) >= 1:
                train_df = (
                    pd.concat([real_train, synth_df], ignore_index=True)
                    .sort_values(TIME_COLUMN)
                    .reset_index(drop=True)
                )
                split = _make_split_frames(
                    train_df=train_df,
                    val_df=real_val,
                    test_df=real_test,
                    feature_cols=feature_cols,
                )
                stats = {
                    "split_policy": "real_only_holdout",
                    "real_rows": int(len(real_df)),
                    "synthetic_rows": int(len(synth_df)),
                }
                return split, stats
        policy = "temporal_all_fallback"

    train_end = max(2, int(n * train_frac))
    val_end = max(train_end + 1, int(n * (train_frac + val_frac)))
    val_end = min(val_end, n - 1)

    train_df = ordered.iloc[:train_end].copy()
    val_df = ordered.iloc[train_end:val_end].copy()
    test_df = ordered.iloc[val_end:].copy()
    if len(val_df) < 1 or len(test_df) < 1:
        raise ValueError("Temporal split produced empty validation or test partition")

    split = _make_split_frames(
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        feature_cols=feature_cols,
    )
    stats = {
        "split_policy": policy,
        "real_rows": int((ordered["_source_type"] == "real").sum()),
        "synthetic_rows": int((ordered["_source_type"] != "real").sum()),
    }
    return split, stats


def _production_gate(summary: dict, min_real_test_rows: int, min_real_test_leaks: int) -> dict:
    trained = [m for m in summary["models"] if m.get("status") == "trained"]
    if not trained:
        return {
            "passed": False,
            "reason": "No models trained",
            "selected_model": None,
        }

    selected = max(
        trained,
        key=lambda m: (m["test"]["business_net_value"], m["test"]["pr_auc"], m["test"]["f1"]),
    )
    conditions = {
        "real_test_rows_ok": summary["data"]["real_test_rows"] >= min_real_test_rows,
        "real_test_leaks_ok": summary["data"]["real_test_leaks"] >= min_real_test_leaks,
        "precision_ok": selected["test"]["precision"] >= 0.6,
        "recall_ok": selected["test"]["recall"] >= 0.6,
        "pr_auc_ok": selected["test"]["pr_auc"] >= 0.6,
        "false_alarm_freq_ok": selected["test"]["false_alarm_frequency_per_day"] <= 2.0,
        "net_value_ok": selected["test"]["business_net_value"] > 0.0,
        "data_sufficiency_ok": summary["data_sufficiency"]["ready"],
    }
    return {
        "passed": bool(all(conditions.values())),
        "selected_model": selected["model"],
        "selected_test_metrics": selected["test"],
        "conditions": conditions,
    }


def _data_sufficiency(
    split: SplitData,
    min_real_train_rows: int,
    min_real_val_rows: int,
    min_real_test_rows: int,
    min_real_test_leaks: int,
) -> dict:
    real_train_rows = int((split.src_train == "real").sum())
    real_val_rows = int((split.src_val == "real").sum())
    real_test_rows = int((split.src_test == "real").sum())
    real_test_mask = (split.src_test == "real").to_numpy()
    real_test_leaks = int(np.sum(split.y_test[real_test_mask]))

    gaps = {
        "real_train_rows_needed": max(0, min_real_train_rows - real_train_rows),
        "real_val_rows_needed": max(0, min_real_val_rows - real_val_rows),
        "real_test_rows_needed": max(0, min_real_test_rows - real_test_rows),
        "real_test_leaks_needed": max(0, min_real_test_leaks - real_test_leaks),
    }
    checks = {
        "real_train_rows_ok": real_train_rows >= min_real_train_rows,
        "real_val_rows_ok": real_val_rows >= min_real_val_rows,
        "real_test_rows_ok": real_test_rows >= min_real_test_rows,
        "real_test_leaks_ok": real_test_leaks >= min_real_test_leaks,
    }
    return {
        "ready": bool(all(checks.values())),
        "minimums": {
            "real_train_rows": min_real_train_rows,
            "real_val_rows": min_real_val_rows,
            "real_test_rows": min_real_test_rows,
            "real_test_leaks": min_real_test_leaks,
        },
        "actuals": {
            "real_train_rows": real_train_rows,
            "real_val_rows": real_val_rows,
            "real_test_rows": real_test_rows,
            "real_test_leaks": real_test_leaks,
        },
        "gaps": gaps,
        "checks": checks,
    }


def _detection_delay_steps(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    positive_idx = np.where(y_true == 1)[0]
    if len(positive_idx) == 0:
        return 0.0

    delays = []
    for idx in positive_idx:
        future = np.where(y_pred[idx:] == 1)[0]
        delays.append(float(future[0]) if len(future) else float(len(y_pred) - idx))
    return float(np.mean(delays))


def _false_alarm_frequency(y_true: np.ndarray, y_pred: np.ndarray, ts: pd.Series) -> float:
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    if fp == 0:
        return 0.0

    clean_ts = pd.to_datetime(ts, utc=True, errors="coerce").dropna()
    if clean_ts.empty:
        return float(fp)

    days = max((clean_ts.max() - clean_ts.min()).total_seconds() / 86400.0, 1.0)
    return float(fp / days)


def _calibration_metrics(y_true: np.ndarray, y_score: np.ndarray) -> dict:
    clipped = np.clip(y_score, 0.0, 1.0)
    brier = float(brier_score_loss(y_true, clipped))
    prob_true, prob_pred = calibration_curve(y_true, clipped, n_bins=8, strategy="quantile")
    ece = float(np.mean(np.abs(prob_true - prob_pred))) if len(prob_true) else 0.0
    return {
        "brier_score": brier,
        "expected_calibration_error": ece,
        "calibration_curve": {
            "prob_true": [float(x) for x in prob_true],
            "prob_pred": [float(x) for x in prob_pred],
        },
    }


def _evaluate_threshold(
    y_true: np.ndarray,
    y_score: np.ndarray,
    ts: pd.Series,
    threshold: float,
    missed_leak_cost: float,
    false_alarm_cost: float,
    early_detection_value: float,
) -> dict:
    y_pred = (y_score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    pr_auc = _safe_pr_auc(y_true, y_score)
    delay = _detection_delay_steps(y_true, y_pred)
    false_alarm_freq = _false_alarm_frequency(y_true, y_pred, ts)

    missed_cost = float(fn) * missed_leak_cost
    false_alarm_total = float(fp) * false_alarm_cost
    early_value = float(tp) * early_detection_value
    net_value = early_value - missed_cost - false_alarm_total

    return {
        "threshold": float(threshold),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": pr_auc,
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "detection_delay_steps": delay,
        "false_alarm_frequency_per_day": false_alarm_freq,
        "business_cost_missed_leaks": missed_cost,
        "business_cost_false_alarms": false_alarm_total,
        "business_value_early_detection": early_value,
        "business_net_value": net_value,
    }


def _threshold_sweep(
    y_true: np.ndarray,
    y_score: np.ndarray,
    ts: pd.Series,
    missed_leak_cost: float,
    false_alarm_cost: float,
    early_detection_value: float,
) -> tuple[list[dict], dict]:
    thresholds = np.linspace(0.1, 0.9, 17)
    rows = [
        _evaluate_threshold(
            y_true,
            y_score,
            ts,
            float(t),
            missed_leak_cost,
            false_alarm_cost,
            early_detection_value,
        )
        for t in thresholds
    ]
    best = max(rows, key=lambda r: (r["business_net_value"], r["f1"]))
    return rows, best


def _fit_isolation_forest(split: SplitData) -> tuple[object, np.ndarray, np.ndarray, dict]:
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(split.x_train)
    x_val_scaled = scaler.transform(split.x_val)
    x_test_scaled = scaler.transform(split.x_test)

    normal_idx = np.where(split.y_train == 0)[0]
    fit_data = x_train_scaled[normal_idx] if len(normal_idx) >= 2 else x_train_scaled
    model = IsolationForest(contamination="auto", random_state=42, n_estimators=300)
    model.fit(fit_data)

    val_raw = -model.score_samples(x_val_scaled)
    test_raw = -model.score_samples(x_test_scaled)
    raw_all = np.concatenate([val_raw, test_raw])
    low = float(np.min(raw_all))
    high = float(np.max(raw_all))
    width = max(high - low, 1e-9)
    val_score = (val_raw - low) / width
    test_score = (test_raw - low) / width
    return model, val_score, test_score, {"scaler": scaler}


def _fit_random_forest(split: SplitData) -> tuple[object, np.ndarray, np.ndarray, dict]:
    model = RandomForestClassifier(n_estimators=400, random_state=42, class_weight="balanced")
    model.fit(split.x_train, split.y_train)
    val_score = model.predict_proba(split.x_val)[:, 1]
    test_score = model.predict_proba(split.x_test)[:, 1]
    return model, val_score, test_score, {}


def _fit_xgboost(split: SplitData) -> tuple[object, np.ndarray, np.ndarray, dict]:
    if XGBClassifier is None:
        raise RuntimeError("xgboost is not installed in this environment")

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="binary:logistic",
        eval_metric="logloss",
        use_label_encoder=False,
        random_state=42,
    )
    model.fit(split.x_train, split.y_train)
    val_score = model.predict_proba(split.x_val)[:, 1]
    test_score = model.predict_proba(split.x_test)[:, 1]
    return model, val_score, test_score, {}


def _advanced_considerations(df: pd.DataFrame, feature_count: int) -> dict:
    has_topology = "node_degree" in df.columns
    unique_sensors = int(df["sensor_node_id"].nunique()) if "sensor_node_id" in df.columns else 0
    n_rows = int(len(df))

    autoencoder_justified = n_rows >= 5000 and feature_count >= 20
    lstm_justified = n_rows >= 8000 and TIME_COLUMN in df.columns
    gnn_justified = has_topology and unique_sensors >= 25 and n_rows >= 5000

    return {
        "autoencoder": {
            "considered": True,
            "justified": autoencoder_justified,
            "reason": (
                "High-dimensional, large-sample anomaly learning possible"
                if autoencoder_justified
                else "Not enough rows/features for stable autoencoder training"
            ),
            "trained": False,
        },
        "lstm": {
            "considered": True,
            "justified": lstm_justified,
            "reason": (
                "Sufficient temporal volume for sequence modeling"
                if lstm_justified
                else "Temporal sample volume too small for robust LSTM"
            ),
            "trained": False,
        },
        "gnn": {
            "considered": True,
            "justified": gnn_justified,
            "reason": (
                "Topology-aware learning likely beneficial"
                if gnn_justified
                else "Topology coverage/scale does not justify GNN complexity"
            ),
            "trained": False,
        },
    }


def _log_mlflow_run(
    run_name: str,
    params: dict,
    metrics: dict,
    artifact_paths: list[Path],
    experiment_name: str,
) -> None:
    if not mlflow:
        return

    mlflow.set_experiment(experiment_name)
    with mlflow.start_run(run_name=run_name):
        for key, value in params.items():
            mlflow.log_param(key, value)
        for key, value in metrics.items():
            if isinstance(value, (int, float, np.floating)):
                mlflow.log_metric(key, float(value))
        for artifact_path in artifact_paths:
            if artifact_path.exists():
                mlflow.log_artifact(str(artifact_path), artifact_path.parent.name)


def _train_and_evaluate_model(
    model_name: str,
    split: SplitData,
    feature_names: list[str],
    output_dir: Path,
    threshold: float,
    missed_leak_cost: float,
    false_alarm_cost: float,
    early_detection_value: float,
    experiment_name: str,
) -> dict:
    model_dir = output_dir / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    if len(np.unique(split.y_train)) < 2 and model_name in {"random_forest", "xgboost"}:
        return {
            "model": model_name,
            "status": "skipped",
            "reason": "Train split has a single class; supervised model not trainable",
        }

    fitters = {
        "isolation_forest": _fit_isolation_forest,
        "random_forest": _fit_random_forest,
        "xgboost": _fit_xgboost,
    }
    if model_name not in fitters:
        raise ValueError(f"Unsupported model: {model_name}")

    try:
        model, val_score, test_score, extras = fitters[model_name](split)
    except Exception as exc:
        return {
            "model": model_name,
            "status": "skipped",
            "reason": str(exc),
        }

    val_metrics = _evaluate_threshold(
        split.y_val,
        val_score,
        split.ts_val,
        threshold,
        missed_leak_cost,
        false_alarm_cost,
        early_detection_value,
    )
    test_metrics = _evaluate_threshold(
        split.y_test,
        test_score,
        split.ts_test,
        threshold,
        missed_leak_cost,
        false_alarm_cost,
        early_detection_value,
    )
    sweep_rows, best_threshold = _threshold_sweep(
        split.y_val,
        val_score,
        split.ts_val,
        missed_leak_cost,
        false_alarm_cost,
        early_detection_value,
    )
    calibration = _calibration_metrics(split.y_test, test_score)

    model_artifact = model_dir / "model.joblib"
    joblib.dump({"model": model, "extras": extras, "features": feature_names}, model_artifact)

    confusion_path = model_dir / "confusion_matrix_test.json"
    confusion_path.write_text(
        json.dumps(test_metrics["confusion_matrix"], indent=2),
        encoding="utf-8",
    )

    threshold_path = model_dir / "threshold_sensitivity_val.csv"
    pd.DataFrame(sweep_rows).to_csv(threshold_path, index=False)

    calibration_path = model_dir / "calibration_test.json"
    calibration_path.write_text(json.dumps(calibration, indent=2), encoding="utf-8")

    report = {
        "model": model_name,
        "status": "trained",
        "threshold_default": threshold,
        "best_threshold_on_val": best_threshold,
        "val": val_metrics,
        "test": test_metrics,
        "calibration": {
            "brier_score": calibration["brier_score"],
            "expected_calibration_error": calibration["expected_calibration_error"],
        },
        "artifacts": {
            "model": str(model_artifact),
            "confusion_matrix": str(confusion_path),
            "threshold_sensitivity": str(threshold_path),
            "calibration": str(calibration_path),
        },
    }

    mlflow_params = {
        "model": model_name,
        "feature_count": len(feature_names),
        "threshold_default": threshold,
        "cost_missed_leak": missed_leak_cost,
        "cost_false_alarm": false_alarm_cost,
        "value_early_detection": early_detection_value,
    }
    mlflow_metrics = {
        "val_precision": val_metrics["precision"],
        "val_recall": val_metrics["recall"],
        "val_f1": val_metrics["f1"],
        "val_pr_auc": val_metrics["pr_auc"],
        "val_detection_delay_steps": val_metrics["detection_delay_steps"],
        "val_false_alarm_frequency_per_day": val_metrics["false_alarm_frequency_per_day"],
        "val_business_net_value": val_metrics["business_net_value"],
        "test_precision": test_metrics["precision"],
        "test_recall": test_metrics["recall"],
        "test_f1": test_metrics["f1"],
        "test_pr_auc": test_metrics["pr_auc"],
        "test_detection_delay_steps": test_metrics["detection_delay_steps"],
        "test_false_alarm_frequency_per_day": test_metrics["false_alarm_frequency_per_day"],
        "test_business_net_value": test_metrics["business_net_value"],
        "test_brier_score": calibration["brier_score"],
        "test_expected_calibration_error": calibration["expected_calibration_error"],
        "best_threshold_val": best_threshold["threshold"],
    }
    _log_mlflow_run(
        run_name=f"{model_name}_suite",
        params=mlflow_params,
        metrics=mlflow_metrics,
        artifact_paths=[model_artifact, confusion_path, threshold_path, calibration_path],
        experiment_name=experiment_name,
    )

    report_path = model_dir / "evaluation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(
    gold_path: str,
    output_dir: str,
    train_frac: float,
    val_frac: float,
    threshold: float,
    missed_leak_cost: float,
    false_alarm_cost: float,
    early_detection_value: float,
    experiment_name: str,
    enforce_real_holdout: bool,
    enforce_production_gate: bool,
    enforce_data_sufficiency: bool,
    min_real_train_rows: int,
    min_real_val_rows: int,
    min_real_test_rows: int,
    min_real_test_leaks: int,
) -> None:
    df = pd.read_parquet(gold_path)
    if TIME_COLUMN not in df.columns:
        raise ValueError(f"{TIME_COLUMN} not found in Gold dataset")
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"{TARGET_COLUMN} not found in Gold dataset")

    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], utc=True, errors="coerce")
    df = df.dropna(subset=[TIME_COLUMN]).copy()
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(int)
    if "_source_type" not in df.columns:
        df["_source_type"] = "real"
    df["_source_type"] = df["_source_type"].fillna("real").astype(str).str.lower()

    feature_names = _candidate_features(df)
    leakage_flags = _check_leakage(feature_names)
    if leakage_flags:
        raise ValueError(f"Potential feature leakage columns detected: {leakage_flags}")

    split, split_stats = _temporal_split(
        df,
        train_frac=train_frac,
        val_frac=val_frac,
        enforce_real_holdout=enforce_real_holdout,
        feature_cols=feature_names,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    models = ["isolation_forest", "random_forest", "xgboost"]
    model_reports = []
    for name in models:
        report = _train_and_evaluate_model(
            model_name=name,
            split=split,
            feature_names=feature_names,
            output_dir=out,
            threshold=threshold,
            missed_leak_cost=missed_leak_cost,
            false_alarm_cost=false_alarm_cost,
            early_detection_value=early_detection_value,
            experiment_name=experiment_name,
        )
        model_reports.append(report)

    advanced = _advanced_considerations(df, feature_count=len(feature_names))
    advanced_path = out / "advanced_model_considerations.json"
    advanced_path.write_text(json.dumps(advanced, indent=2), encoding="utf-8")

    if mlflow:
        _log_mlflow_run(
            run_name="advanced_model_considerations",
            params={"feature_count": len(feature_names), "row_count": len(df)},
            metrics={},
            artifact_paths=[advanced_path],
            experiment_name=experiment_name,
        )

    summary = {
        "data": {
            "rows": len(df),
            "feature_count": len(feature_names),
            "train_rows": len(split.x_train),
            "val_rows": len(split.x_val),
            "test_rows": len(split.x_test),
            "real_train_rows": int((split.src_train == "real").sum()),
            "real_val_rows": int((split.src_val == "real").sum()),
            "real_test_rows": int((split.src_test == "real").sum()),
            "synthetic_train_rows": int((split.src_train != "real").sum()),
            "synthetic_val_rows": int((split.src_val != "real").sum()),
            "synthetic_test_rows": int((split.src_test != "real").sum()),
            "real_test_leaks": int(np.sum(split.y_test[(split.src_test == "real").to_numpy()])),
            "split_policy": split_stats["split_policy"],
            "target": TARGET_COLUMN,
        },
        "business_inputs": {
            "cost_missed_leak": missed_leak_cost,
            "cost_false_alarm": false_alarm_cost,
            "value_early_detection": early_detection_value,
        },
        "models": model_reports,
        "advanced_models": advanced,
    }

    summary["data_sufficiency"] = _data_sufficiency(
        split=split,
        min_real_train_rows=min_real_train_rows,
        min_real_val_rows=min_real_val_rows,
        min_real_test_rows=min_real_test_rows,
        min_real_test_leaks=min_real_test_leaks,
    )

    gate = _production_gate(
        summary,
        min_real_test_rows=min_real_test_rows,
        min_real_test_leaks=min_real_test_leaks,
    )
    summary["production_gate"] = gate

    summary_path = out / "model_suite_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    gate_path = out / "production_gate.json"
    gate_path.write_text(json.dumps(gate, indent=2), encoding="utf-8")

    if mlflow:
        _log_mlflow_run(
            run_name="production_gate",
            params={
                "split_policy": summary["data"]["split_policy"],
                "min_real_train_rows": min_real_train_rows,
                "min_real_val_rows": min_real_val_rows,
                "min_real_test_rows": min_real_test_rows,
                "min_real_test_leaks": min_real_test_leaks,
            },
            metrics={
                "gate_passed": 1.0 if gate["passed"] else 0.0,
                "data_sufficiency_ready": 1.0 if summary["data_sufficiency"]["ready"] else 0.0,
                "real_train_rows_gap": float(
                    summary["data_sufficiency"]["gaps"]["real_train_rows_needed"]
                ),
                "real_val_rows_gap": float(
                    summary["data_sufficiency"]["gaps"]["real_val_rows_needed"]
                ),
                "real_test_rows_gap": float(
                    summary["data_sufficiency"]["gaps"]["real_test_rows_needed"]
                ),
                "real_test_leaks_gap": float(
                    summary["data_sufficiency"]["gaps"]["real_test_leaks_needed"]
                ),
            },
            artifact_paths=[gate_path, summary_path],
            experiment_name=experiment_name,
        )

    if enforce_data_sufficiency and not summary["data_sufficiency"]["ready"]:
        raise RuntimeError(
            "Data sufficiency check failed; see model_suite_summary.json "
            "for required additional real data"
        )

    if enforce_production_gate and not gate["passed"]:
        raise RuntimeError("Production gate failed; see production_gate.json for details")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path", required=True)
    parser.add_argument("--output-dir", default="ml/training/artifacts/model_suite")
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--val-frac", type=float, default=0.2)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--cost-missed-leak", type=float, default=5000.0)
    parser.add_argument("--cost-false-alarm", type=float, default=500.0)
    parser.add_argument("--value-early-detection", type=float, default=2500.0)
    parser.add_argument("--experiment-name", default="water-intel-model-suite")
    parser.add_argument("--enforce-real-holdout", action="store_true")
    parser.add_argument("--enforce-production-gate", action="store_true")
    parser.add_argument("--enforce-data-sufficiency", action="store_true")
    parser.add_argument("--min-real-train-rows", type=int, default=200)
    parser.add_argument("--min-real-val-rows", type=int, default=30)
    parser.add_argument("--min-real-test-rows", type=int, default=100)
    parser.add_argument("--min-real-test-leaks", type=int, default=10)
    args = parser.parse_args()

    if not os.path.exists(args.gold_path):
        raise FileNotFoundError(f"Gold dataset not found: {args.gold_path}")

    main(
        gold_path=args.gold_path,
        output_dir=args.output_dir,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
        threshold=args.threshold,
        missed_leak_cost=args.cost_missed_leak,
        false_alarm_cost=args.cost_false_alarm,
        early_detection_value=args.value_early_detection,
        experiment_name=args.experiment_name,
        enforce_real_holdout=args.enforce_real_holdout,
        enforce_production_gate=args.enforce_production_gate,
        enforce_data_sufficiency=args.enforce_data_sufficiency,
        min_real_train_rows=args.min_real_train_rows,
        min_real_val_rows=args.min_real_val_rows,
        min_real_test_rows=args.min_real_test_rows,
        min_real_test_leaks=args.min_real_test_leaks,
    )