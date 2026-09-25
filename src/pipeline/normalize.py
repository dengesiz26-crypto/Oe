"""
Normalizes raw provider payloads into our canonical fixture/odds schema,
running everything through validation.py (reject/quarantine bad rows)
before it ever reaches feature building.
"""
from __future__ import annotations
from src.core.validation import validate_fixture, validate_odds, dedupe_events


def normalize_fixture(raw: dict, provider: str) -> dict:
    """Provider-specific field mapping happens here — this is the single
    place that changes if a provider renames a field, so the rest of the
    pipeline never touches raw provider payloads directly."""
    return {
        "fixture_id": f"{provider}:{raw.get('id')}",
        "provider": provider,
        "provider_event_id": raw.get("id"),
        "home_team": raw.get("home_team") or raw.get("homeTeam") or raw.get("home", {}).get("name"),
        "away_team": raw.get("away_team") or raw.get("awayTeam") or raw.get("away", {}).get("name"),
        "kickoff_utc": raw.get("kickoff_utc") or raw.get("date") or raw.get("commence_time"),
        "league_id": raw.get("league_id") or raw.get("leagueId"),
        "league_name": raw.get("league_name") or raw.get("leagueName"),
        "season_id": raw.get("season_id") or raw.get("seasonId"),  # canonical, never invented
        "score": raw.get("score"),
    }


def normalize_and_validate(raw_fixtures: list[dict], provider: str) -> tuple[list[dict], list[dict]]:
    normalized = [normalize_fixture(r, provider) for r in raw_fixtures]
    normalized = dedupe_events(normalized)

    good, rejected = [], []
    for fx in normalized:
        result = validate_fixture(fx)
        if result.ok:
            good.append(fx)
        else:
            rejected.append({"fixture": fx, "reasons": result.reasons})
    return good, rejected
