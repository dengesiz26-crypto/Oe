"""
Calibration + scoring metrics used to decide whether a model/feature is
actually earning its place in production (walk-forward OOS evaluation).
"""
from __future__ import annotations
import math


def brier_score(predicted_probs: list[float], outcomes: list[int]) -> float:
    """Lower is better. outcomes[i] in {0,1}."""
    n = len(predicted_probs)
    return sum((p - o) ** 2 for p, o in zip(predicted_probs, outcomes)) / n


def log_loss(predicted_probs: list[float], outcomes: list[int], eps: float = 1e-12) -> float:
    n = len(predicted_probs)
    total = 0.0
    for p, o in zip(predicted_probs, outcomes):
        p = min(max(p, eps), 1 - eps)
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / n


def expected_calibration_error(predicted_probs: list[float], outcomes: list[int], n_bins: int = 10) -> float:
    bins = [[] for _ in range(n_bins)]
    for p, o in zip(predicted_probs, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, o))
    n = len(predicted_probs)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        avg_p = sum(p for p, _ in b) / len(b)
        avg_o = sum(o for _, o in b) / len(b)
        ece += (len(b) / n) * abs(avg_p - avg_o)
    return ece


def roi(stakes: list[float], odds: list[float], outcomes: list[int]) -> float:
    """Simple flat-stake ROI, outcomes[i] in {0,1} (1 = bet won)."""
    staked = sum(stakes)
    returned = sum(s * o if win else 0 for s, o, win in zip(stakes, odds, outcomes))
    if staked == 0:
        return 0.0
    return (returned - staked) / staked
