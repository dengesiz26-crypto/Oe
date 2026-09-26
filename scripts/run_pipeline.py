#!/usr/bin/env python3
"""
Entry point invoked by the GitHub Actions workflow
(.github/workflows/ai-football.yml).

    START
      -> load persistent state
      -> check provider quotas
      -> fetch only necessary updates (fixtures, league names, odds)
      -> normalize + validate
      -> build features (Poisson/Elo/Dixon-Coles inputs)
      -> generate probabilities -> value -> risk -> decision
      -> build coupons
      -> settle any finished fixtures against real results
      -> export docs/data/*.json
      -> git commit (done by the workflow, not this script)

This orchestrator wires the real modules together. Provider clients
raise ProviderError when an API key isn't configured, so running this
without secrets set is a safe, informative dry run rather than a crash.
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from src.core.api_manager import ApiManager
from src.core.config import settings
from src.pipeline.fetch import (
    fetch_upcoming_fixtures, fetch_finished_fixtures,
    fetch_league_name_lookup, fetch_event_odds,
)
from src.pipeline.normalize import normalize_and_validate, enrich_league_names
from src.pipeline.predict import predict_fixture
from src.pipeline.settle import run_settlement
from src.pipeline.export_json import export_all
from src.engine.coupon_engine import Candidate, tier_candidate, build_coupons
from src.models.poisson import TeamStrength
from src.models.elo import EloState


def main() -> None:
    manager = ApiManager()
    now = datetime.now(timezone.utc)

    print("[1/7] Checking provider quotas...")
    for status in manager.provider_status():
        print("   ", status)

    print("[2/7] Fetching upcoming fixtures (cache-aware)...")
    date_from = now.strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=3)).strftime("%Y-%m-%d")
    raw_upcoming = fetch_upcoming_fixtures(manager, date_from, date_to)
    fixtures, rejected = normalize_and_validate(raw_upcoming, "goaldir")
    print(f"    {len(fixtures)} valid fixtures, {len(rejected)} rejected")
    if rejected[:3]:
        for r in rejected[:3]:
            print("     rejected example:", r["reasons"])

    print("[3/7] Resolving league names...")
    league_lookup = fetch_league_name_lookup(manager)
    fixtures = enrich_league_names(fixtures, league_lookup)
    print(f"    {len(league_lookup)} leagues in lookup")

    print("[4/7] Fetching odds + generating predictions...")
    elo = EloState()
    all_predictions = []
    for fx in fixtures:
        # NOTE: real attack/defence strengths come from the feature-building
        # stage (recent goals for/against, opponent-adjusted). Placeholder
        # league-average strengths are used here until historical data has
        # been bootstrapped (see README "What to build next").
        home_strength = TeamStrength(attack=1.0, defence=1.0)
        away_strength = TeamStrength(attack=1.0, defence=1.0)
        market_odds = fetch_event_odds(manager, fx["fixture_id"], fx["provider_event_id"])
        preds = predict_fixture(fx, home_strength, away_strength, elo, market_odds)
        all_predictions.extend(preds)

    print("[5/7] Building coupons...")
    candidates = [
        Candidate(
            fixture_id=p["match_id"], market=p["market"], probability=p["probability"],
            odds=p["odds"] or 0.0, edge=p["edge"], risk_level=p["risk_level"],
            classification=p["classification"],
            tier=tier_candidate(p["classification"], p["risk_level"], p["decision"]),
        )
        for p in all_predictions if p["odds"] is not None
    ]
    coupons = build_coupons(candidates)
    print(f"    {len(coupons)} coupon(s) generated" if coupons else "    NO COUPON (no qualifying candidates)")

    print("[6/7] Settling finished fixtures...")
    finished_from = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    raw_finished = fetch_finished_fixtures(manager, finished_from, date_from)
    finished, _ = normalize_and_validate(raw_finished, "goaldir")
    settlement = run_settlement(finished)
    print("   ", settlement["settled_count"], "episodes settled")

    print("[7/7] Exporting docs/data/*.json...")
    export_all(all_predictions, coupons, settlement["backtest_report"], manager.provider_status())
    print("Done.")


if __name__ == "__main__":
    main()
