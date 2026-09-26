"""
Fetch stage: pulls only what's actually needed (incremental, cache-aware,
priority-tagged) through the ApiManager rather than re-downloading
everything on every run (spec section 8-9).
"""
from __future__ import annotations
from src.core.api_manager import ApiManager, ApiRequest, PRIORITY_PREDICTION, PRIORITY_CRITICAL, PRIORITY_ENRICHMENT
from src.providers.goaldir import GoalDirProvider
from src.core.config import settings

# GoalDir's per-match consensus odds (from /events/{id}/odds/) use their own
# key names; this maps them onto our internal market vocabulary
# (src/engine/market_engine.py). Markets GoalDir doesn't quote in the free
# consensus response (0.5 line, home/away-team-over lines) are simply absent
# from the result — predict.py already treats a missing price as "no odds",
# which the risk engine correctly turns into a NO BET rather than a fabricated one.
_GOALDIR_ODDS_KEY_MAP = {
    "home_win": "1x2_home",
    "draw": "1x2_draw",
    "away_win": "1x2_away",
    "over_15_goals": "over_1.5",
    "under_15_goals": "under_1.5",
    "over_25_goals": "over_2.5",
    "under_25_goals": "under_2.5",
    "over_35_goals": "over_3.5",
    "under_35_goals": "under_3.5",
    "btts_yes": "btts_yes",
    "btts_no": "btts_no",
}


def fetch_upcoming_fixtures(manager: ApiManager, date_from: str, date_to: str) -> list[dict]:
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key=f"goaldir:fixtures:{date_from}:{date_to}",
        fetch_fn=lambda: _call_with_headers(provider.get_fixtures, date_from, date_to, status="upcoming"),
        priority=PRIORITY_PREDICTION,
    )
    return manager.request(req) or []


def fetch_finished_fixtures(manager: ApiManager, date_from: str, date_to: str) -> list[dict]:
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key=f"goaldir:finished:{date_from}:{date_to}",
        fetch_fn=lambda: _call_with_headers(provider.get_fixtures, date_from, date_to, status="finished"),
        priority=PRIORITY_CRITICAL,  # result settlement is P0
        force_refresh=True,
    )
    return manager.request(req) or []


def fetch_league_name_lookup(manager: ApiManager) -> dict[int, str]:
    """GoalDir's /events/ list carries league_id but not league_name (see
    normalize.py::enrich_league_names). This resolves the mapping once per
    run via /leagues/, cached ~24h since competition identity barely
    changes — exactly the "50,000 matches every run" problem this project
    is explicitly trying to avoid, applied to leagues instead of fixtures."""
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key="goaldir:leagues:all",
        fetch_fn=lambda: _call_with_headers(provider.get_leagues),
        priority=PRIORITY_ENRICHMENT,
    )
    leagues = manager.request(req) or []
    return {lg["id"]: lg.get("name") for lg in leagues if "id" in lg}


def fetch_event_odds(manager: ApiManager, fixture_id: str, provider_event_id: str) -> dict[str, float]:
    """Fetches one fixture's consensus odds and maps them onto our internal
    market keys. Cached per-fixture (~3 min, matching GoalDir's own odds
    refresh cadence) so re-running the pipeline within that window doesn't
    re-spend a call on unchanged prices."""
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key=f"goaldir:odds:{provider_event_id}",
        fetch_fn=lambda: _call_with_headers(provider.get_event_odds, provider_event_id),
        priority=PRIORITY_PREDICTION,
    )
    payload = manager.request(req)
    if not payload:
        return {}
    consensus = payload.get("odds", {})
    return {
        _GOALDIR_ODDS_KEY_MAP[k]: v
        for k, v in consensus.items()
        if k in _GOALDIR_ODDS_KEY_MAP and v is not None
    }


def _call_with_headers(fn, *args, **kwargs):
    """ApiManager expects fetch_fn() -> (payload, headers); our provider
    methods already return that tuple, so this just forwards args/kwargs
    through a lambda-friendly wrapper."""
    return fn(*args, **kwargs)
