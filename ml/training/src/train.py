from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

from ml.training.src.evaluate import evaluate
from ml.training.src.features import build_training_frame

try:
    import mlflow
except ImportError:  # pragma: no cover
    mlflow = None


def main(gold_path: str, model_output: str) -> None:
    df = pd.read_parquet(gold_path)
    x, y = build_training_frame(df)

    n_classes = int(y.nunique())
    test_size = 0.2
    if len(y) < 20:
        test_size = 0.4

    class_counts = y.value_counts()
    can_stratify = (
        n_classes > 1
        and class_counts.min() >= 2
        and math.ceil(len(y) * test_size) >= n_classes
    )

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=test_size,
        random_state=42,
        stratify=y if can_stratify else None,
    )

    model = RandomForestClassifier(n_estimators=300, random_state=42, class_weight="balanced")
    model.fit(x_train, y_train)

    y_score = model.predict_proba(x_test)[:, 1]
    result = evaluate(y_test.to_numpy(), y_score)

    if mlflow:
        mlflow.set_experiment("water-intel-leak-detection")
        with mlflow.start_run():
            mlflow.log_param("model", "RandomForestClassifier")
            mlflow.log_metric("precision", result.precision)
            mlflow.log_metric("recall", result.recall)
            mlflow.log_metric("pr_auc", result.pr_auc)
            mlflow.log_metric("detection_delay_steps", result.detection_delay_steps)

    output_path = Path(model_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)

    print(
        {
            "precision": result.precision,
            "recall": result.recall,
            "pr_auc": result.pr_auc,
            "detection_delay_steps": result.detection_delay_steps,
            "model_path": str(output_path),
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-path", required=True)
    parser.add_argument("--model-output", default="ml/training/artifacts/leak_model.joblib")
    args = parser.parse_args()

    if not os.path.exists(args.gold_path):
        raise FileNotFoundError(f"Gold dataset not found: {args.gold_path}")

    main(args.gold_path, args.model_output)
