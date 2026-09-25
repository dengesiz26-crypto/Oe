"""
API-Football client — second, independent football data source used for
targeted verification (e.g. "BSD says lineup missing -> check here"),
NOT for bulk full-endpoint pulls (free plan: 100 req/day, 10 req/min).
"""
from __future__ import annotations
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings


class ApiFootballProvider(BaseProvider):
    name = "api_football"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.api_football_key
        self.base_url = base_url or settings.api_football_base_url

    def _headers(self) -> dict:
        return {"x-apisports-key": self.api_key}

    def _get(self, path: str, params: dict | None = None) -> tuple[dict, dict]:
        if not self.api_key:
            raise ProviderError("API_FOOTBALL_KEY not set")
        import requests
        resp = requests.get(self.base_url + path, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 429:
            raise RateLimited("api_football 429")
        if resp.status_code >= 400:
            raise ProviderError(f"api_football {resp.status_code}: {resp.text[:200]}")
        return resp.json(), dict(resp.headers)

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        data, headers = self._get("fixtures", {"from": date_from, "to": date_to})
        return data.get("response", []), headers

    def get_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        out, headers = [], {}
        for fid in fixture_ids:  # deliberately one at a time: this provider is a verifier, not bulk source
            data, headers = self._get("odds", {"fixture": fid})
            out.extend(data.get("response", []))
        return out, headers

    def get_lineup(self, fixture_id: str) -> tuple[list[dict], dict]:
        data, headers = self._get("fixtures/lineups", {"fixture": fixture_id})
        return data.get("response", []), headers
