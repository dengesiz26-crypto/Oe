"""
Dixon-Coles low-score correlation correction.

Plain independent-Poisson underestimates how correlated low scores
(0-0, 1-0, 0-1, 1-1) really are. Dixon & Coles (1997) introduce a tau
adjustment applied to those four cells only, plus a time-decay weighting
for how much older matches count when fitting attack/defence strengths.
"""
from __future__ import annotations
import math


def tau(x: int, y: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lambda_home * lambda_away * rho
    if x == 0 and y == 1:
        return 1 + lambda_home * rho
    if x == 1 and y == 0:
        return 1 + lambda_away * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def apply_dixon_coles(matrix: list[list[float]], lambda_home: float, lambda_away: float,
                       rho: float = -0.06) -> list[list[float]]:
    """rho is typically small and negative; fit it from historical data via
    max-likelihood in the training pipeline rather than hardcoding it long-term."""
    adjusted = [row[:] for row in matrix]
    for x in range(2):
        for y in range(2):
            adjusted[x][y] *= tau(x, y, lambda_home, lambda_away, rho)
    total = sum(sum(row) for row in adjusted)
    if total > 0:
        adjusted = [[v / total for v in row] for row in adjusted]
    return adjusted


def time_decay_weight(days_ago: int, half_life_days: int = 180) -> float:
    """Exponential decay so recent matches count more when fitting team
    strengths — half_life_days is a hyperparameter to tune in backtesting."""
    return math.exp(-math.log(2) * days_ago / half_life_days)
