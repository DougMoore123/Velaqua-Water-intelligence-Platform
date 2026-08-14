from __future__ import annotations

import argparse
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

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
    "_row_hash",
    "pressure_unit",
    "flow_unit",
    "demand_unit",
    "pressure_unit_standard",
    "flow_unit_standard",
    "demand_unit_standard",
}


def _candidate_features(df: pd.DataFrame) -> list[str]:
    excluded = ID_COLUMNS | {TIME_COLUMN, TARGET_COLUMN, "leak_label"}
    cols = [c for c in df.columns if c not in excluded]
    numeric = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    return numeric


def _check_leakage(features: list[str]) -> list[str]:
    flagged = []
    for name in features:
        lowered = name.lower()
        if "target" in lowered or "future" in lowered:
            flagged.append(name)
    return flagged


def _temporal_split(df: pd.DataFrame, train_frac: float, val_frac: float):
    ordered = df.sort_values(TIME_COLUMN).reset_index(drop=True)
    n = len(ordered)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    train_df = ordered.iloc[:train_end].copy()
    val_df = ordered.iloc[train_end:val_end].copy()
    test_df = ordered.iloc[val_end:].copy()
    return train_df, val_df, test_df


def _metrics(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> dict:
    y_pred = (y_score >= threshold).astype(int)
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, y_score)),
    }


def main(
    gold_path: str,
    model_output: str,
    train_frac: float,
    val_frac: float,
    prediction_horizon_steps: int,
) -> None:
    df = pd.read_parquet(gold_path)
    if TIME_COLUMN not in df.columns:
        raise ValueError(f"{TIME_COLUMN} not found in Gold dataset")
    if TARGET_COLUMN not in df.columns:
        raise ValueError(f"{TARGET_COLUMN} not found in Gold dataset")

    df[TIME_COLUMN] = pd.to_datetime(df[TIME_COLUMN], utc=True, errors="coerce")
    df = df.dropna(subset=[TIME_COLUMN]).copy()
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(int)

    train_df, val_df, test_df = _temporal_split(df, train_frac=train_frac, val_frac=val_frac)
    if len(train_df) < 2 or len(val_df) < 1 or len(test_df) < 1:
        raise ValueError("Not enough rows for temporal train/val/test split")

    features = _candidate_features(df)
    leakage_flags = _check_leakage(features)
    if leakage_flags:
        raise ValueError(f"Potential feature leakage columns detected: {leakage_flags}")

    x_train = train_df[features].fillna(0)
    y_train = train_df[TARGET_COLUMN].to_numpy()
    x_val = val_df[features].fillna(0)
    y_val = val_df[TARGET_COLUMN].to_numpy()
    x_test = test_df[features].fillna(0)
    y_test = test_df[TARGET_COLUMN].to_numpy()

    # Fit preprocessing on train only.
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_val_scaled = scaler.transform(x_val)
    x_test_scaled = scaler.transform(x_test)

    train_prior = float(np.mean(y_train)) if len(y_train) else 0.0
    baseline_val_score = np.full(shape=len(y_val), fill_value=train_prior, dtype=float)
    baseline_test_score = np.full(shape=len(y_test), fill_value=train_prior, dtype=float)
    baseline_val = _metrics(y_val, baseline_val_score, threshold=train_prior)
    baseline_test = _metrics(y_test, baseline_test_score, threshold=train_prior)

    model = LogisticRegression(max_iter=2000, class_weight="balanced")
    model.fit(x_train_scaled, y_train)

    val_score = model.predict_proba(x_val_scaled)[:, 1]
    test_score = model.predict_proba(x_test_scaled)[:, 1]
    val_metrics = _metrics(y_val, val_score)
    test_metrics = _metrics(y_test, test_score)

    output_path = Path(model_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "scaler": scaler,
            "features": features,
            "target": TARGET_COLUMN,
            "prediction_horizon_steps": prediction_horizon_steps,
        },
        output_path,
    )

    summary = {
        "rows": {"train": len(train_df), "val": len(val_df), "test": len(test_df)},
        "target": TARGET_COLUMN,
        "prediction_horizon_steps": prediction_horizon_steps,
        "feature_count": len(features),
        "baseline_val": baseline_val,
        "baseline_test": baseline_test,
        "logreg_val": val_metrics,
        "logreg_test": test_metrics,
        "model_path": str(output_path),
    }

    if mlflow:
        mlflow.set_experiment("water-intel-logistic-baseline")
        with mlflow.start_run():
            mlflow.log_param("model", "LogisticRegression")
            mlflow.log_param("prediction_horizon_steps", prediction_horizon_steps)
            mlflow.log_param("feature_count", len(features))
            mlflow.log_metric("baseline_val_pr_auc", baseline_val["pr_auc"])
            mlflow.log_metric("baseline_test_pr_auc", baseline_test["pr_auc"])
            mlflow.log_metric("logreg_val_pr_auc", val_metrics["pr_auc"])
            mlflow.log_metric("logreg_test_pr_auc", test_metrics["pr_auc"])

    print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path", required=True)
    parser.add_argument(
        "--model-output",
        default="ml/training/artifacts/logreg_baseline.joblib",
    )
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--val-frac", type=float, default=0.2)
    parser.add_argument("--prediction-horizon-steps", type=int, default=1)
    args = parser.parse_args()

    if not os.path.exists(args.gold_path):
        raise FileNotFoundError(f"Gold dataset not found: {args.gold_path}")

    main(
        args.gold_path,
        args.model_output,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
        prediction_horizon_steps=args.prediction_horizon_steps,
    )
