from __future__ import annotations

from scripts.monitor_operational_metrics import _data_quality, _schema_changes


def test_data_quality_detects_missing_and_duplicates() -> None:
    rows = [
        {"a": 1, "b": None},
        {"a": 1, "b": None},
        {"a": 2, "b": 4},
    ]
    result = _data_quality(rows)
    assert result["missing_rate"] > 0
    assert result["duplicate_rate"] > 0


def test_schema_changes_identifies_added_and_removed_columns() -> None:
    baseline = [{"a": 1, "b": 2}]
    current = [{"a": 1, "c": 3}]
    result = _schema_changes(baseline, current)
    assert result["added_columns"] == ["c"]
    assert result["removed_columns"] == ["b"]
