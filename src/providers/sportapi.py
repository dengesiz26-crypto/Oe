"""
SportAPI.ai client — third-layer verification source (fixtures, standings,
leagues, H2H, player stats). Path-based REST API, not query-filtered lists.

Verified against https://sportapi.ai/docs (2026-09-25).

Key facts:
  - Base URL is https://sportapi.ai/api  — NOT the bare sportapi.ai domain.
  - Auth: Authorization: Bearer <token>, required for some endpoints (account/
    profile); the data endpoints used here (fixtures, standings, leagues, h2h)
    are read with the same header regardless — harmless if not required.
  - Endpoints are path-parameterized, not query-filtered:
      GET /fixtures/date/{date}            (YYYY-MM-DD)
      GET /fixtures/{id}
      GET /fixtures/{id}/events
      GET /fixtures/{id}/stats
      GET /fixtures/{id}/lineups
      GET /fixtures/h2h/{team1}/{team2}
      GET /standings/leagues
      GET /standings/{leagueId}
      GET /leagues
      GET /leagues/{id}
  - Every response wraps the payload behind a top-level "success" boolean
    (`{"success": true, ...}`); check it before trusting the rest of the body.
  - No documented rate-limit response headers — we still route every call
    through the shared ApiManager/cache/priority system so a slow provider
    doesn't get hammered even without a header telling us to back off.
"""
from __future__ import annotations
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings


class SportApiProvider(BaseProvider):
    name = "sportapi"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.sportapi_key
        self.base_url = base_url or settings.sportapi_base_url

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        import requests
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        resp = requests.get(self.base_url + path, headers=self._headers(), params=clean_params, timeout=20)

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            raise RateLimited(
                f"sportapi 429: {resp.text[:200]}",
                retry_after=float(retry_after) if retry_after else None,
            )
        if resp.status_code >= 400:
            raise ProviderError(f"sportapi {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        if data.get("success") is False:
            raise ProviderError(f"sportapi business error: {data}")
        return data, dict(resp.headers)

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        """SportAPI has no date-range endpoint — fetches one day at a time
        (date_from..date_to inclusive) and concatenates. Keep ranges short;
        this provider is a verifier, not a bulk source."""
        from datetime import datetime, timedelta
        start = datetime.fromisoformat(date_from)
        end = datetime.fromisoformat(date_to)

        all_fixtures: list[dict] = []
        headers: dict = {}
        day = start
        while day <= end:
            data, headers = self._get(f"fixtures/date/{day.strftime('%Y-%m-%d')}")
            all_fixtures.extend(data.get("fixtures", []))
            day += timedelta(days=1)
        return all_fixtures, headers

    def get_fixture_detail(self, fixture_id: str) -> tuple[dict, dict]:
        data, headers = self._get(f"fixtures/{fixture_id}")
        return data.get("fixture", {}), headers

    def get_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        return [], {}  # SportAPI has no odds endpoint in the documented API

    def get_h2h(self, team1_id: str, team2_id: str) -> tuple[dict, dict]:
        return self._get(f"fixtures/h2h/{team1_id}/{team2_id}")

    def get_standings(self, league_id: str) -> tuple[dict, dict]:
        data, headers = self._get(f"standings/{league_id}")
        return data.get("data", {}), headers

    def get_leagues(self) -> tuple[list[dict], dict]:
        data, headers = self._get("leagues")
        return data.get("data", []), headers
