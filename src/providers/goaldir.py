"""
GoalDir / BSD provider client — primary data source (fixtures, teams,
leagues, standings, statistics, xG, lineups, H2H, odds, best odds,
predictions, live).

Verified against the real docs on 2026-09-25:
  https://goaldir.com/docs/football/
  https://goaldir.com/docs/football/events/
  https://goaldir.com/docs/football/leagues/
  https://goaldir.com/docs/football/odds-predictions/
  https://goaldir.com/docs/conventions/

Key facts baked into this client:
  - Base URL: https://sports.bzzoiro.com/api/v2/   (v2 is current; v1 is legacy)
  - Auth:     Authorization: Token <API_KEY>
  - Pagination: {count, next, previous, results}, limit/offset (default 50, max 200)
  - Error shape: {"error": true, "status": <code>, "detail": "..."}
  - /events/ list fields actually returned: id, league_id, season_id, home_team,
    away_team, event_date, status, home_score, away_score, live_websocket — NOT
    league_name, NOT a nested "score" object, and the kickoff field is
    `event_date`, not `date`/`kickoff_utc`/`commence_time`. league_name is
    resolved separately via /leagues/.
  - Unknown query params are REJECTED with 400 (not silently ignored), so this
    client only ever sends parameters the docs list as accepted.
  - Rate limiting: two independent limits —
      * daily quota (7,500/day on the free football tier since 2026-08-17),
        reported via IETF structured-field headers:
          RateLimit-Policy: "football";q=7500;w=86400
          RateLimit:        "football";r=7213;t=52800
        (r = requests remaining, t = seconds to reset)
      * per-IP burst limit (25 req/s, burst 110) on the cached read endpoints —
        we don't model this one explicitly; our own call rate is nowhere near it.
    Both flavors of 429 carry a `Retry-After` header and a JSON `code` field:
    "rate_limited" (burst) or "taster_exhausted" (daily quota gone).
  - We deliberately do NOT use GoalDir's own /predictions/ endpoint as our
    primary prediction source — it may be pulled in as a comparison signal
    only, per this project's explicit rule.
"""
from __future__ import annotations
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings

# Every query parameter GoalDir's /events/ list actually accepts (from the
# 400 error body's `accepted_parameters`, and from the resource docs). Sending
# anything outside this set gets the whole request rejected, so we validate
# client-side too and fail fast with a clear message instead of a round trip.
_EVENTS_ACCEPTED_PARAMS = {
    "date_from", "date_to", "league_id", "season_id", "status",
    "team_id", "team_name", "stage", "round", "limit", "offset",
}


class GoalDirProvider(BaseProvider):
    name = "goaldir"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.goaldir_api_key
        self.base_url = base_url or settings.goaldir_base_url

    def _headers(self) -> dict:
        return {"Authorization": f"Token {self.api_key}"}

    def _get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        if not self.api_key:
            raise ProviderError("GOALDIR_API_KEY not set")
        import requests  # imported lazily so the module loads without the dep installed

        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        resp = requests.get(self.base_url + path, headers=self._headers(), params=clean_params, timeout=20)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise RateLimited(
                f"goaldir 429: {resp.text[:200]}",
                retry_after=float(retry_after) if retry_after else None,
            )
        if resp.status_code >= 400:
            # GoalDir's error envelope: {"error": true, "status": ..., "detail": "..."}
            raise ProviderError(f"goaldir {resp.status_code}: {resp.text[:300]}")

        return resp.json(), dict(resp.headers)

    def _get_all_pages(self, path: str, params: dict, max_pages: int = 10) -> tuple[list[dict], dict]:
        """Follows GoalDir's {count, next, previous, results} pagination until
        exhausted or max_pages is hit — a safety cap so a huge unfiltered
        query can't spin the pipeline forever."""
        results: list[dict] = []
        headers: dict = {}
        offset = params.get("offset", 0)
        limit = params.get("limit", 50)

        for _ in range(max_pages):
            page_params = {**params, "limit": limit, "offset": offset}
            data, headers = self._get(path, page_params)
            page_results = data.get("results", [])
            results.extend(page_results)
            if not data.get("next") or not page_results:
                break
            offset += limit

        return results, headers

    # ---- events ----------------------------------------------------------

    def get_fixtures(self, date_from: str, date_to: str, league_id: str | None = None,
                      season_id: str | None = None, status: str | None = None) -> tuple[list[dict], dict]:
        params = {
            "date_from": date_from, "date_to": date_to,
            "league_id": league_id, "season_id": season_id, "status": status,
        }
        assert set(params) <= _EVENTS_ACCEPTED_PARAMS
        return self._get_all_pages("events/", params)

    def get_live(self, league_id: str | None = None) -> tuple[list[dict], dict]:
        data, headers = self._get("events/live/", {"league_id": league_id})
        return data.get("results", data if isinstance(data, list) else []), headers

    def get_event_detail(self, event_id: str) -> tuple[dict, dict]:
        return self._get(f"events/{event_id}/")

    # ---- odds --------------------------------------------------------------
    # Free-tier odds are consensus-only (one row per market, not per bookmaker).

    def get_event_odds(self, event_id: str) -> tuple[dict, dict]:
        """Per-match shortcut: /events/{id}/odds/ — the simplest way to get a
        single fixture's full consensus price set (home_win, draw, away_win,
        over/under 1.5/2.5/3.5, btts_yes/no) in one call. See
        https://goaldir.com/docs/football/events/#odds-and-when-they-refresh
        """
        return self._get(f"events/{event_id}/odds/")

    def get_odds_feed(self, league_id: str | None = None, season_id: str | None = None,
                       market: str | None = None, updated_after: str | None = None,
                       limit: int = 200, offset: int = 0) -> tuple[list[dict], dict]:
        """Bulk odds feed: /odds/ — one row per event x market x outcome.
        Pass `updated_after` (ISO timestamp of the newest row you already have)
        to fetch only what changed since your last poll, per GoalDir's own
        guidance, instead of re-reading the whole book every run."""
        params = {
            "league_id": league_id, "season_id": season_id, "market": market,
            "updated_after": updated_after, "limit": limit, "offset": offset,
        }
        data, headers = self._get("odds/", params)
        return data.get("results", []), headers

    # ---- leagues / seasons / standings -------------------------------------

    def get_leagues(self, country: str | None = None) -> tuple[list[dict], dict]:
        data, headers = self._get("leagues/", {"country": country})
        return data.get("results", data if isinstance(data, list) else []), headers

    def get_current_season(self, league_id: str) -> tuple[dict, dict]:
        """GET /leagues/{id}/season/ — resolve the current season id rather
        than hardcoding one, as the docs explicitly recommend."""
        return self._get(f"leagues/{league_id}/season/")

    def get_standings(self, league_id: str, season_id: str) -> tuple[dict, dict]:
        return self._get(f"leagues/{league_id}/standings/", {"season_id": season_id})

    # ---- comparison-only: GoalDir's own model, never our primary signal ----

    def get_prediction(self, event_id: str) -> tuple[dict, dict]:
        return self._get(f"events/{event_id}/prediction/")
