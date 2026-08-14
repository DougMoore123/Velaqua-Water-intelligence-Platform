from __future__ import annotations

from typing import Tuple

import pandas as pd

FEATURE_COLUMNS = [
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


def build_training_frame(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    missing = [c for c in FEATURE_COLUMNS + ["leak_label"] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = df[FEATURE_COLUMNS].fillna(0)
    y = df["leak_label"].astype(int)
    return x, y
