"""
API-Football client — second, independent football data source used for
targeted verification (e.g. "BSD says lineup missing -> check here"),
NOT for bulk full-endpoint pulls (free plan: 100 req/day, 10 req/min).

Verified against https://www.api-football.com/documentation-v3 and the
official "How rate limit works" / "get started" articles (2026-09-25).

Key facts:
  - Direct host: https://v3.football.api-sports.io/
    Auth header: x-apisports-key: <API_KEY>
  - Via RapidAPI instead: host api-football-v1.p.rapidapi.com, headers
    x-rapidapi-key + x-rapidapi-host (set API_FOOTBALL_VIA_RAPIDAPI=1)
  - Every response wraps data as:
      {"get": ..., "parameters": [...], "errors": [...] or {...},
       "results": N, "paging": {"current": 1, "total": 1}, "response": [...]}
    The actual payload is always in "response".
  - Rate-limit headers on every response:
      x-ratelimit-requests-limit / x-ratelimit-requests-remaining  (daily)
      X-RateLimit-Limit / X-RateLimit-Remaining                    (per-minute)
  - /fixtures requires a sensible parameter combination — a bare date works
    ("date=2026-09-27" lists that day's fixtures across leagues), or
    league+season combined with date / from+to / round for a scoped window.
    A from/to range with no league or season is not a documented, reliable
    combination, so this client always requires season alongside from/to.
  - GET-only API. No POST/PUT/DELETE anywhere.
"""
from __future__ import annotations
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings

_RAPIDAPI_HOST = "api-football-v1.p.rapidapi.com"
_RAPIDAPI_BASE_URL = f"https://{_RAPIDAPI_HOST}/v3/"


class ApiFootballProvider(BaseProvider):
    name = "api_football"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 via_rapidapi: bool | None = None):
        self.api_key = api_key or settings.api_football_key
        self.via_rapidapi = settings.api_football_via_rapidapi if via_rapidapi is None else via_rapidapi
        self.base_url = base_url or (_RAPIDAPI_BASE_URL if self.via_rapidapi else settings.api_football_base_url)

    def _headers(self) -> dict:
        if self.via_rapidapi:
            return {"x-rapidapi-key": self.api_key, "x-rapidapi-host": _RAPIDAPI_HOST}
        return {"x-apisports-key": self.api_key}

    def _get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        if not self.api_key:
            raise ProviderError("API_FOOTBALL_KEY not set")
        import requests
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        resp = requests.get(self.base_url + path, headers=self._headers(), params=clean_params, timeout=20)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise RateLimited(
                f"api_football 429: {resp.text[:200]}",
                retry_after=float(retry_after) if retry_after else None,
            )
        if resp.status_code >= 400:
            raise ProviderError(f"api_football {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        errors = data.get("errors")
        if errors:  # API-Football returns 200 with populated "errors" on some failures
            raise ProviderError(f"api_football business error: {errors}")
        return data, dict(resp.headers)

    def get_status(self) -> tuple[dict, dict]:
        """GET /status — account/plan/quota info, does not count against quota."""
        return self._get("status")

    def get_fixtures(self, date_from: str, date_to: str, league: str | None = None,
                      season: str | None = None) -> tuple[list[dict], dict]:
        if league and season:
            params = {"league": league, "season": season, "from": date_from, "to": date_to}
        else:
            # No documented "from/to with no league/season" combination — fall
            # back to one date at a time (a bare `date` param is well-supported
            # and returns that day's fixtures across every league).
            params = {"date": date_from}
        data, headers = self._get("fixtures", params)
        return data.get("response", []), headers

    def get_fixtures_by_date(self, date: str) -> tuple[list[dict], dict]:
        data, headers = self._get("fixtures", {"date": date})
        return data.get("response", []), headers

    def get_odds(self, fixture_id: str) -> tuple[list[dict], dict]:
        data, headers = self._get("odds", {"fixture": fixture_id})
        return data.get("response", []), headers

    def get_lineup(self, fixture_id: str) -> tuple[list[dict], dict]:
        data, headers = self._get("fixtures/lineups", {"fixture": fixture_id})
        return data.get("response", []), headers

    def get_team_statistics(self, league: str, season: str, team: str) -> tuple[dict, dict]:
        data, headers = self._get("teams/statistics", {"league": league, "season": season, "team": team})
        return data.get("response", {}), headers
