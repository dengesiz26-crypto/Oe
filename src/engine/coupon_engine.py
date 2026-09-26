"""
Coupon engine.

Builds a candidate pool (Strong / Playable / Watch), then selects a
coupon (if any good candidates exist) respecting:
  - same-market cap: max 2 coupons carrying an identical (fixture, market)
  - same-fixture cap: a fixture may appear in at most 3 coupons
  - different markets on the same fixture are allowed
  - no duplicate coupon regenerated within the same ~3h production window
  - no fixed leg count: "NO COUPON" is a valid, expected output
"""
from __future__ import annotations
from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class Candidate:
    fixture_id: str
    market: str
    probability: float
    odds: float
    edge: float
    risk_level: str
    classification: str
    tier: str  # "A_STRONG" | "B_PLAYABLE" | "C_WATCH"


def tier_candidate(classification: str, risk_level: str, decision: str) -> str:
    if decision != "PLAY":
        return "C_WATCH"
    if classification in ("BANKO", "STANDARD") and risk_level == "LOW":
        return "A_STRONG"
    if classification in ("STANDARD", "IDEAL") and risk_level in ("LOW", "MEDIUM"):
        return "B_PLAYABLE"
    return "C_WATCH"


def joint_probability(legs: list[Candidate]) -> float:
    # naive independence assumption; replace with a correlation-aware
    # estimate once enough settled episodes exist to fit cross-market
    # correlations (e.g. same-fixture 1X2 vs O/U legs are NOT independent)
    p = 1.0
    for leg in legs:
        p *= leg.probability
    return p


def build_coupons(candidates: list[Candidate], max_legs: int = 4,
                   min_legs: int = 2, top_n: int = 3) -> list[dict]:
    pool = [c for c in candidates if c.tier in ("A_STRONG", "B_PLAYABLE")]
    if len(pool) < min_legs:
        return []  # NO COUPON is a legitimate output

    pool.sort(key=lambda c: (c.tier != "A_STRONG", -c.probability))

    coupons = []
    fixture_appearances: dict[str, int] = {}
    market_appearances: dict[tuple, int] = {}

    for size in range(min(max_legs, len(pool)), min_legs - 1, -1):
        for combo in combinations(pool[: min(10, len(pool))], size):
            fixtures = {c.fixture_id for c in combo}
            if len(fixtures) != size:
                continue  # no same-fixture-multiple-legs within one coupon

            if any(fixture_appearances.get(c.fixture_id, 0) >= 3 for c in combo):
                continue
            if any(market_appearances.get((c.fixture_id, c.market), 0) >= 2 for c in combo):
                continue

            jp = joint_probability(list(combo))
            coupons.append({
                "legs": [c.__dict__ for c in combo],
                "joint_probability": round(jp, 4),
                "leg_count": size,
            })
            for c in combo:
                fixture_appearances[c.fixture_id] = fixture_appearances.get(c.fixture_id, 0) + 1
                market_appearances[(c.fixture_id, c.market)] = market_appearances.get((c.fixture_id, c.market), 0) + 1

            if len(coupons) >= top_n:
                return coupons
    return coupons
