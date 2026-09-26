"""
Value/edge calculation: compares our fair odds (1/probability) against the
market price. This never overrides the MIN_ODDS floor — a high-probability
pick at an odds-too-low price is a probability read, not a betting
recommendation (see project spec section 13).
"""
from __future__ import annotations
from dataclasses import dataclass
from src.core.config import settings


@dataclass
class ValueResult:
    fair_odds: float
    edge: float           # (market_odds / fair_odds) - 1
    meets_min_odds: bool
    has_positive_edge: bool


def evaluate_value(probability: float, market_odds: float | None) -> ValueResult:
    fair_odds = 1 / probability if probability > 0 else float("inf")
    if market_odds is None:
        return ValueResult(fair_odds=fair_odds, edge=0.0, meets_min_odds=False, has_positive_edge=False)

    edge = (market_odds / fair_odds) - 1
    return ValueResult(
        fair_odds=fair_odds,
        edge=edge,
        meets_min_odds=market_odds >= settings.min_odds,
        has_positive_edge=edge > 0,
    )
