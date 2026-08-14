from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np

DEFAULT_FEATURES = [
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
MAX_ROWS = 10000

model = None
model_extras: dict[str, Any] = {}
model_features: list[str] = DEFAULT_FEATURES
model_name = "unknown"


def _error(code: str, message: str, details: list[str] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
        }
    }


def _resolve_model_path() -> Path:
    model_dir = Path(os.getenv("AZUREML_MODEL_DIR", "."))
    model_filename = os.getenv("MODEL_FILENAME", "leak_model.joblib")

    candidates = []
    if model_dir.is_file():
        candidates.append(model_dir)
    else:
        candidates.append(model_dir / model_filename)
        candidates.append(model_dir / "model.joblib")
        candidates.append(model_dir / "leak_model.joblib")

    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError(f"No model artifact found in {model_dir}")


def _extract_rows(payload: dict[str, Any]) -> tuple[np.ndarray | None, list[str]]:
    rows = payload.get("data")
    if rows is None:
        return None, ["Missing required field: data"]
    if not isinstance(rows, list):
        return None, ["Field data must be a list"]
    if len(rows) == 0:
        return np.empty((0, len(model_features))), []
    if len(rows) > MAX_ROWS:
        return None, [f"Payload exceeds max rows ({MAX_ROWS})"]

    parsed: list[list[float]] = []
    errors: list[str] = []
    expected_cols = len(model_features)
    for i, row in enumerate(rows):
        if isinstance(row, dict):
            missing = [f for f in model_features if f not in row]
            if missing:
                errors.append(f"Row {i} missing fields: {missing}")
                continue
            try:
                values = [float(row[f]) for f in model_features]
            except (TypeError, ValueError):
                errors.append(f"Row {i} contains non-numeric feature values")
                continue
        elif isinstance(row, list):
            if len(row) != expected_cols:
                errors.append(f"Row {i} must contain {expected_cols} feature values")
                continue
            try:
                values = [float(v) for v in row]
            except (TypeError, ValueError):
                errors.append(f"Row {i} contains non-numeric feature values")
                continue
        else:
            errors.append(f"Row {i} must be an object or list")
            continue

        if any(np.isnan(v) or np.isinf(v) for v in values):
            errors.append(f"Row {i} contains NaN or infinite values")
            continue
        parsed.append(values)

    if errors:
        return None, errors
    return np.array(parsed, dtype=float), []


def _predict_scores(features: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]

    if hasattr(model, "score_samples"):
        transformed = features
        scaler = model_extras.get("scaler")
        if scaler is not None:
            transformed = scaler.transform(features)
        raw = -model.score_samples(transformed)
        low = float(np.min(raw))
        high = float(np.max(raw))
        width = max(high - low, 1e-9)
        return (raw - low) / width

    raise RuntimeError("Loaded model does not expose predict_proba or score_samples")


def init() -> None:
    global model, model_extras, model_features, model_name
    model_path = _resolve_model_path()
    loaded = joblib.load(model_path)

    if isinstance(loaded, dict) and "model" in loaded:
        model = loaded["model"]
        model_extras = loaded.get("extras", {})
        model_features = loaded.get("features") or DEFAULT_FEATURES
        model_name = loaded.get("model_name", getattr(model, "__class__", type(model)).__name__)
    else:
        model = loaded
        model_extras = {}
        model_features = DEFAULT_FEATURES
        model_name = getattr(model, "__class__", type(model)).__name__


def run(raw_data: str):
    if model is None:
        return _error("MODEL_NOT_INITIALIZED", "Call init() before run().")

    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        return _error("INVALID_JSON", "Request body is not valid JSON", [str(exc)])

    if not isinstance(payload, dict):
        return _error("INVALID_PAYLOAD", "Top-level payload must be a JSON object")

    features, errors = _extract_rows(payload)
    if errors:
        return _error("INVALID_INPUT", "Input schema validation failed", errors)

    if features is None:
        return _error("INVALID_INPUT", "No valid feature rows provided")
    if len(features) == 0:
        return {
            "predictions": [],
            "model": {"name": model_name, "feature_count": len(model_features)},
            "n_rows": 0,
        }

    try:
        scores = _predict_scores(features)
    except Exception as exc:  # pragma: no cover
        return _error("INFERENCE_FAILED", "Model inference failed", [str(exc)])

    predictions = [
        {
            "score": float(score),
            "is_leak": int(score >= 0.5),
        }
        for score in scores
    ]
    return {
        "predictions": predictions,
        "model": {
            "name": model_name,
            "feature_count": len(model_features),
        },
        "n_rows": len(predictions),
    }
