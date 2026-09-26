"""
Prediction episodes: the append-only record every prediction is written
to, and later settled against the real result. This is the raw material
for calibration and model learning (spec section 16-17) — NOT a simple
"won -> increase weight" reinforcement loop.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class Episode:
    match_id: str
    market: str
    probability: float
    odds: float
    fair_odds: float
    edge: float
    risk_score: float
    classification: str
    decision: str
    model_version: str
    data_quality: float
    created_at: float = None
    result: str = "PENDING"  # WIN | LOSS | VOID | PENDING
    settled_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class EpisodeStore:
    def __init__(self, path: str = "data/state/episodes.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, episode: Episode) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(episode), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def settle_pending(self, results_by_match: dict[str, dict]) -> int:
        """results_by_match: {match_id: {"home_goals": int, "away_goals": int}}.
        Rewrites the file with PENDING episodes resolved against real results."""
        rows = self.load_all()
        settled_count = 0
        for row in rows:
            if row["result"] != "PENDING":
                continue
            res = results_by_match.get(row["match_id"])
            if res is None:
                continue
            outcome = _resolve_market(row["market"], res)
            if outcome is not None:
                row["result"] = "WIN" if outcome else "LOSS"
                row["settled_at"] = time.time()
                settled_count += 1

        with open(self.path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return settled_count


def _resolve_market(market: str, result: dict) -> bool | None:
    h, a = result.get("home_goals"), result.get("away_goals")
    if h is None or a is None:
        return None
    total = h + a

    if market == "1x2_home":
        return h > a
    if market == "1x2_draw":
        return h == a
    if market == "1x2_away":
        return a > h
    if market.startswith("over_"):
        line = float(market.split("_")[1])
        return total > line
    if market.startswith("under_"):
        line = float(market.split("_")[1])
        return total < line
    if market == "btts_yes":
        return h > 0 and a > 0
    if market == "btts_no":
        return not (h > 0 and a > 0)
    if market.startswith("home_team_over_"):
        line = float(market.split("_")[-1])
        return h > line
    if market.startswith("away_team_over_"):
        line = float(market.split("_")[-1])
        return a > line
    return None
