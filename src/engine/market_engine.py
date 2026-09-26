"""
Builds the full candidate market list for a fixture from the raw
probability output (1X2 + the wide O/U ladder + team-goals + BTTS), in
the shape the value/risk/coupon engines expect.
"""
from __future__ import annotations

MARKET_LADDER_LINES = (0.5, 1.5, 2.5, 3.5)


def build_candidate_markets(probs: dict, fixture_id: str) -> list[dict]:
    out = []

    for side, p in probs["1x2"].items():
        out.append({"fixture_id": fixture_id, "market": f"1x2_{side}", "probability": p})

    for line, ou in probs["over_under"].items():
        out.append({"fixture_id": fixture_id, "market": f"over_{line}", "probability": ou["over"]})
        out.append({"fixture_id": fixture_id, "market": f"under_{line}", "probability": ou["under"]})

    for line, p in probs["home_team_over"].items():
        out.append({"fixture_id": fixture_id, "market": f"home_team_over_{line}", "probability": p})
    for line, p in probs["away_team_over"].items():
        out.append({"fixture_id": fixture_id, "market": f"away_team_over_{line}", "probability": p})

    out.append({"fixture_id": fixture_id, "market": "btts_yes", "probability": probs["btts"]["yes"]})
    out.append({"fixture_id": fixture_id, "market": "btts_no", "probability": probs["btts"]["no"]})

    return out
