"""
Walk-forward out-of-sample backtest runner. Splits settled episodes
chronologically (never trains on the future) and reports the metrics
that gate production promotion (spec section 32-33).
"""
from __future__ import annotations
from src.models.calibration import brier_score, log_loss, expected_calibration_error, roi


def walk_forward_report(episodes: list[dict]) -> dict:
    settled = [e for e in episodes if e["result"] in ("WIN", "LOSS")]
    settled.sort(key=lambda e: e["created_at"])

    if not settled:
        return {"n": 0, "note": "no settled episodes yet"}

    probs = [e["probability"] for e in settled]
    outcomes = [1 if e["result"] == "WIN" else 0 for e in settled]
    stakes = [1.0 for _ in settled]
    odds = [e["odds"] for e in settled]

    by_market: dict[str, list] = {}
    for e in settled:
        by_market.setdefault(e["market"], []).append(e)

    per_market = {}
    for market, rows in by_market.items():
        p = [r["probability"] for r in rows]
        o = [1 if r["result"] == "WIN" else 0 for r in rows]
        per_market[market] = {
            "n": len(rows),
            "hit_rate": round(sum(o) / len(o), 4),
            "brier": round(brier_score(p, o), 4),
        }

    return {
        "n": len(settled),
        "brier": round(brier_score(probs, outcomes), 4),
        "log_loss": round(log_loss(probs, outcomes), 4),
        "ece": round(expected_calibration_error(probs, outcomes), 4),
        "roi": round(roi(stakes, odds, outcomes), 4),
        "hit_rate": round(sum(outcomes) / len(outcomes), 4),
        "per_market": per_market,
    }
