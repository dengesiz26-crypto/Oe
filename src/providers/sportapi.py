"""
SportAPI.ai client — third-layer verification source (fixtures, live
scores, standings, events, lineups, statistics, H2H, player info).
REST + Bearer auth.
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
        return {"Authorization": f"Bearer {self.api_key}"}

    def _get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        if not self.api_key:
            raise ProviderError("SPORTAPI_KEY not set")
        import requests
        resp = requests.get(self.base_url + path, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 429:
            raise RateLimited("sportapi 429")
        if resp.status_code >= 400:
            raise ProviderError(f"sportapi {resp.status_code}: {resp.text[:200]}")
        return resp.json(), dict(resp.headers)

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        data, headers = self._get("fixtures", {"from": date_from, "to": date_to})
        return data.get("data", []), headers

    def get_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        return [], {}  # SportAPI here used for stats/H2H verification, not odds

    def get_h2h(self, team_a: str, team_b: str) -> tuple[list[dict], dict]:
        data, headers = self._get("h2h", {"team_a": team_a, "team_b": team_b})
        return data.get("data", []), headers
