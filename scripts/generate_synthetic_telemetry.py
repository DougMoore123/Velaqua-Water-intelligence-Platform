from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_CORE_COLUMNS = [
    "timestamp",
    "node_id",
    "pressure",
    "flow",
    "demand",
    "leak_label",
]

UNIT_DEFAULTS = {
    "pressure_unit": "psi",
    "flow_unit": "gpm",
    "demand_unit": "gpm",
}


def _load_seed_data(input_dir: str) -> pd.DataFrame:
    base = Path(input_dir)
    if not base.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    frames: list[pd.DataFrame] = []
    for csv_path in sorted(base.glob("*.csv")):
        df = pd.read_csv(csv_path)
        if all(c in df.columns for c in REQUIRED_CORE_COLUMNS):
            for col_name, default_value in UNIT_DEFAULTS.items():
                if col_name not in df.columns:
                    df[col_name] = default_value
            frames.append(df[REQUIRED_CORE_COLUMNS + list(UNIT_DEFAULTS.keys())].copy())

    if not frames:
        raise ValueError(
            "No telemetry CSV files found with required columns in input directory"
        )

    seed_df = pd.concat(frames, ignore_index=True)
    seed_df["timestamp"] = pd.to_datetime(seed_df["timestamp"], utc=True, errors="coerce")
    seed_df = seed_df.dropna(subset=["timestamp"]).copy()
    seed_df["leak_label"] = seed_df["leak_label"].astype(int)
    return seed_df


def _augment(seed_df: pd.DataFrame, multiplier: int, leak_boost: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n_out = max(len(seed_df) * multiplier, len(seed_df))
    sampled_idx = rng.integers(low=0, high=len(seed_df), size=n_out)
    sampled = seed_df.iloc[sampled_idx].copy().reset_index(drop=True)

    jitter_minutes = rng.integers(low=-5, high=6, size=n_out)
    sampled["timestamp"] = sampled["timestamp"] + pd.to_timedelta(jitter_minutes, unit="m")

    pressure_noise = rng.normal(loc=1.0, scale=0.04, size=n_out)
    flow_noise = rng.normal(loc=1.0, scale=0.06, size=n_out)
    demand_noise = rng.normal(loc=1.0, scale=0.06, size=n_out)

    sampled["pressure"] = np.clip(sampled["pressure"].astype(float) * pressure_noise, 0.0, None)
    sampled["flow"] = np.clip(sampled["flow"].astype(float) * flow_noise, 0.0, None)
    sampled["demand"] = np.clip(sampled["demand"].astype(float) * demand_noise, 0.0, None)

    base_positive_rate = float(seed_df["leak_label"].mean())
    synthetic_positive_rate = min(base_positive_rate * leak_boost, 0.35)
    sampled["leak_label"] = (rng.random(n_out) < synthetic_positive_rate).astype(int)

    leak_mask = sampled["leak_label"] == 1
    sampled.loc[leak_mask, "pressure"] = np.clip(
        sampled.loc[leak_mask, "pressure"] * rng.uniform(0.75, 0.95, size=int(leak_mask.sum())),
        0.0,
        None,
    )
    sampled.loc[leak_mask, "flow"] = np.clip(
        sampled.loc[leak_mask, "flow"] * rng.uniform(1.05, 1.35, size=int(leak_mask.sum())),
        0.0,
        None,
    )

    sampled = sampled.sort_values(["timestamp", "node_id"]).reset_index(drop=True)
    sampled["timestamp"] = sampled["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return sampled


def main(input_dir: str, output_path: str, multiplier: int, leak_boost: float, seed: int) -> None:
    seed_df = _load_seed_data(input_dir)
    synth_df = _augment(seed_df, multiplier=multiplier, leak_boost=leak_boost, seed=seed)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    synth_df.to_csv(out_path, index=False)

    print(
        {
            "seed_rows": len(seed_df),
            "synthetic_rows": len(synth_df),
            "seed_leak_rate": float(seed_df["leak_label"].mean()),
            "synthetic_leak_rate": float(synth_df["leak_label"].mean()),
            "output_path": str(out_path),
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="data/raw")
    parser.add_argument("--output-path", default="data/raw_synthetic/synth_telemetry.csv")
    parser.add_argument("--multiplier", type=int, default=40)
    parser.add_argument("--leak-boost", type=float, default=1.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    main(
        input_dir=args.input_dir,
        output_path=args.output_path,
        multiplier=args.multiplier,
        leak_boost=args.leak_boost,
        seed=args.seed,
    )