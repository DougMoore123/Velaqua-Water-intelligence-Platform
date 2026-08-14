from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import average_precision_score, precision_score, recall_score


@dataclass
class EvalResult:
    precision: float
    recall: float
    pr_auc: float
    detection_delay_steps: float


def estimate_detection_delay(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    positive_idx = np.where(y_true == 1)[0]
    if len(positive_idx) == 0:
        return 0.0

    delays = []
    for idx in positive_idx:
        future = np.where(y_pred[idx:] == 1)[0]
        delays.append(float(future[0]) if len(future) else float(len(y_pred) - idx))
    return float(np.mean(delays))


def evaluate(y_true: np.ndarray, y_score: np.ndarray, threshold: float = 0.5) -> EvalResult:
    y_pred = (y_score >= threshold).astype(int)
    return EvalResult(
        precision=float(precision_score(y_true, y_pred, zero_division=0)),
        recall=float(recall_score(y_true, y_pred, zero_division=0)),
        pr_auc=float(average_precision_score(y_true, y_score)),
        detection_delay_steps=estimate_detection_delay(y_true, y_pred),
    )
