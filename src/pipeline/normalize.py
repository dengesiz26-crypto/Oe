"""
Normalizes raw provider payloads into our canonical fixture/odds schema,
running everything through validation.py (reject/quarantine bad rows)
before it ever reaches feature building.

Field mapping is provider-specific and lives ONLY here — the rest of the
pipeline never touches a raw provider payload directly, so a provider
renaming a field is a one-file fix.

GoalDir's real /events/ shape (per https://goaldir.com/docs/football/events/,
confirmed 2026-09-25):
    {id, league_id, season_id, home_team, away_team, event_date, status,
     home_score, away_score, live_websocket, ...}
Note this does NOT include league_name (resolved separately, see
`enrich_league_names` below), and score is two flat fields, not a nested
object — normalize_fixture builds the nested {"home":..,"away":..} shape our
internal engine expects.
"""
from __future__ import annotations
from src.core.validation import validate_fixture, dedupe_events


def _extract_score(raw: dict, provider: str) -> dict | None:
    if provider == "goaldir":
        h, a = raw.get("home_score"), raw.get("away_score")
    elif provider == "api_football":
        goals = raw.get("goals", {})
        h, a = goals.get("home"), goals.get("away")
    elif provider == "sportapi":
        h, a = raw.get("home_score"), raw.get("away_score")
    else:
        h, a = raw.get("home_score"), raw.get("away_score")

    if h is None and a is None:
        return None
    return {"home": h, "away": a}


def normalize_fixture(raw: dict, provider: str) -> dict:
    """Provider-specific field mapping happens here — this is the single
    place that changes if a provider renames a field, so the rest of the
    pipeline never touches raw provider payloads directly."""
    if provider == "goaldir":
        return {
            "fixture_id": f"goaldir:{raw.get('id')}",
            "provider": provider,
            "provider_event_id": raw.get("id"),
            "home_team": raw.get("home_team"),
            "away_team": raw.get("away_team"),
            "kickoff_utc": raw.get("event_date"),
            "league_id": raw.get("league_id"),
            "league_name": raw.get("league_name"),  # usually absent; filled by enrich_league_names
            "season_id": raw.get("season_id"),      # canonical, never invented
            "status": raw.get("status"),
            "score": _extract_score(raw, provider),
        }

    if provider == "api_football":
        fixture = raw.get("fixture", {})
        league = raw.get("league", {})
        teams = raw.get("teams", {})
        return {
            "fixture_id": f"api_football:{fixture.get('id')}",
            "provider": provider,
            "provider_event_id": fixture.get("id"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "kickoff_utc": fixture.get("date"),
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "season_id": league.get("season"),
            "status": (fixture.get("status") or {}).get("short"),
            "score": _extract_score(raw, provider),
        }

    if provider == "sportapi":
        return {
            "fixture_id": f"sportapi:{raw.get('id')}",
            "provider": provider,
            "provider_event_id": raw.get("id"),
            "home_team": raw.get("home_team"),
            "away_team": raw.get("away_team"),
            "kickoff_utc": raw.get("date") or raw.get("kickoff"),
            "league_id": raw.get("league_id"),
            "league_name": raw.get("league_name"),
            "season_id": raw.get("season_id"),
            "status": raw.get("status"),
            "score": _extract_score(raw, provider),
        }

    raise ValueError(f"unknown provider: {provider}")


def enrich_league_names(fixtures: list[dict], league_lookup: dict[int, str]) -> list[dict]:
    """GoalDir's /events/ list has no league_name — fill it in from a
    separately-fetched {league_id: league_name} map (built once from
    /leagues/ and cached for ~24h, since league identity barely changes).
    Fixtures whose league_id has no match in the lookup keep league_name as
    None rather than being silently dropped; validation only requires
    league_id, so they still pass through."""
    for fx in fixtures:
        if not fx.get("league_name") and fx.get("league_id") in league_lookup:
            fx["league_name"] = league_lookup[fx["league_id"]]
    return fixtures


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
