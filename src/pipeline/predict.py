"""
Turns fixtures + team strengths into full per-fixture predictions:
Poisson score matrix -> Dixon-Coles correction -> market probabilities
-> Elo cross-check -> value/risk/decision per candidate market.
"""
from __future__ import annotations
from src.models.poisson import TeamStrength, expected_goals, score_matrix, market_probabilities
from src.models.dixon_coles import apply_dixon_coles
from src.models.elo import EloState
from src.engine.market_engine import build_candidate_markets
from src.engine.value_engine import evaluate_value
from src.engine.risk_engine import RiskInputs, evaluate as evaluate_risk

MODEL_VERSION = "v0.1"


def predict_fixture(fixture: dict, home_strength: TeamStrength, away_strength: TeamStrength,
                     elo: EloState, market_odds: dict[str, float], data_quality: float = 1.0) -> list[dict]:
    lam_home, lam_away = expected_goals(home_strength, away_strength)
    matrix = score_matrix(lam_home, lam_away)
    matrix = apply_dixon_coles(matrix, lam_home, lam_away)
    probs = market_probabilities(matrix)

    elo_probs = elo.win_probability(fixture["home_team"], fixture["away_team"])
    disagreement = max(abs(probs["1x2"][k] - elo_probs[k]) for k in ("home", "draw", "away"))

    candidates = build_candidate_markets(probs, fixture["fixture_id"])

    results = []
    for cand in candidates:
        odds = market_odds.get(cand["market"])
        value = evaluate_value(cand["probability"], odds)
        risk_inputs = RiskInputs(
            data_completeness=data_quality,
            model_disagreement=disagreement,
        )
        risk = evaluate_risk(cand["probability"], value, risk_inputs)

        results.append({
            "match_id": fixture["fixture_id"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "kickoff_utc": fixture.get("kickoff_utc"),
            "league": fixture.get("league_name"),
            "market": cand["market"],
            "probability": round(cand["probability"], 4),
            "odds": odds,
            "fair_odds": round(value.fair_odds, 3) if value.fair_odds != float("inf") else None,
            "edge": round(value.edge, 4),
            "classification": risk.classification,
            "risk_level": risk.risk_level,
            "risk_score": risk.risk_score,
            "decision": risk.decision,
            "notes": risk.notes,
            "model_version": MODEL_VERSION,
            "data_quality": data_quality,
        })
    return results
