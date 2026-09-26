"""
Result-settlement stage: fetch finished fixtures, resolve every PENDING
episode, mark coupons WON/LOST/VOID, and feed settled episodes into the
calibration/backtest report (spec section 16-20).
"""
from __future__ import annotations
from src.learning.episodes import EpisodeStore
from src.learning.backtest import walk_forward_report


def run_settlement(finished_fixtures: list[dict]) -> dict:
    results_by_match = {
        fx["fixture_id"]: {"home_goals": fx["score"]["home"], "away_goals": fx["score"]["away"]}
        for fx in finished_fixtures
        if fx.get("score") and fx["score"].get("home") is not None
    }

    store = EpisodeStore()
    settled_count = store.settle_pending(results_by_match)
    report = walk_forward_report(store.load_all())

    return {"settled_count": settled_count, "backtest_report": report}
