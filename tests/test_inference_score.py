from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier

from ml.deployment import score


def _build_model_artifact(path: Path) -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=(300, len(score.DEFAULT_FEATURES)))
    y = (x[:, 0] + 0.2 * x[:, 1] > 0).astype(int)

    model = RandomForestClassifier(n_estimators=40, random_state=7)
    model.fit(x, y)
    artifact = {
        "model": model,
        "features": score.DEFAULT_FEATURES,
        "extras": {},
        "model_name": "rf_test_model",
    }
    joblib.dump(artifact, path)


def _init_model(tmp_path: Path, monkeypatch) -> None:
    model_path = tmp_path / "leak_model.joblib"
    _build_model_artifact(model_path)
    monkeypatch.setenv("AZUREML_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_FILENAME", "leak_model.joblib")

    score.model = None
    score.model_extras = {}
    score.model_features = score.DEFAULT_FEATURES
    score.model_name = "unknown"
    score.init()


def _valid_row(value: float = 1.0) -> dict:
    return {k: value for k in score.DEFAULT_FEATURES}


def test_model_startup(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    assert score.model is not None
    assert score.model_name == "rf_test_model"


def test_valid_request_dict_rows(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    payload = {"data": [_valid_row(0.2), _valid_row(0.8)]}
    result = score.run(json.dumps(payload))

    assert "error" not in result
    assert result["n_rows"] == 2
    assert len(result["predictions"]) == 2
    assert set(result["predictions"][0].keys()) == {"score", "is_leak"}


def test_valid_request_list_rows(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    row = [0.3] * len(score.DEFAULT_FEATURES)
    payload = {"data": [row, row]}
    result = score.run(json.dumps(payload))

    assert "error" not in result
    assert result["n_rows"] == 2


def test_invalid_json(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    result = score.run("not-json")
    assert result["error"]["code"] == "INVALID_JSON"


def test_missing_fields(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    payload = {"data": [{"pressure": 1.0}]}
    result = score.run(json.dumps(payload))
    assert result["error"]["code"] == "INVALID_INPUT"


def test_incorrect_data_types(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    row = _valid_row(1.0)
    row["flow"] = "bad"
    result = score.run(json.dumps({"data": [row]}))
    assert result["error"]["code"] == "INVALID_INPUT"


def test_empty_payload(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    result = score.run(json.dumps({"data": []}))
    assert "error" not in result
    assert result["predictions"] == []


def test_large_payload(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    payload = {"data": [_valid_row(0.5) for _ in range(2000)]}
    result = score.run(json.dumps(payload))
    assert "error" not in result
    assert result["n_rows"] == 2000


def test_too_large_payload_rejected(tmp_path, monkeypatch):
    _init_model(tmp_path, monkeypatch)
    payload = {"data": [_valid_row(0.5) for _ in range(score.MAX_ROWS + 1)]}
    result = score.run(json.dumps(payload))
    assert result["error"]["code"] == "INVALID_INPUT"


def test_model_not_initialized_error():
    score.model = None
    result = score.run(json.dumps({"data": []}))
    assert result["error"]["code"] == "MODEL_NOT_INITIALIZED"
