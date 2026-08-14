from __future__ import annotations

import json
from pathlib import Path


def test_inference_input_schema_contains_required_fields() -> None:
    schema = json.loads(
        Path("ml/deployment/schemas/input_schema.json").read_text(encoding="utf-8")
    )
    assert "required" in schema
    assert "data" in schema["required"]


def test_inference_output_schema_contains_predictions() -> None:
    schema = json.loads(
        Path("ml/deployment/schemas/output_schema.json").read_text(encoding="utf-8")
    )
    assert "oneOf" in schema
    variants = schema["oneOf"]
    prediction_variants = [
        item
        for item in variants
        if "properties" in item and "predictions" in item["properties"]
    ]
    assert prediction_variants
