"""
GoalDir / BSD provider client — primary data source (fixtures, teams,
leagues, standings, statistics, xG, lineups, H2H, odds, best odds, live).

Base URL: https://sports.bzzoiro.com/api/v2/
Auth: header "Authorization: Token <API_KEY>"

We deliberately do NOT use GoalDir's own /predictions endpoint as our
prediction source — it may be pulled in as a comparison signal only.
Actual HTTP calls are left as thin wrappers so this file stays a clean,
documented mapping onto the real API; wire in `requests` (or httpx) here
when GOALDIR_API_KEY is set.
"""
from __future__ import annotations
import os
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings


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
        resp = requests.get(self.base_url + path, headers=self._headers(), params=params, timeout=20)
        if resp.status_code == 429:
            raise RateLimited("goaldir 429")
        if resp.status_code >= 400:
            raise ProviderError(f"goaldir {resp.status_code}: {resp.text[:200]}")
        return resp.json(), dict(resp.headers)

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        data, headers = self._get("events", {"date_from": date_from, "date_to": date_to})
        return data.get("results", []), headers

    def get_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        data, headers = self._get("odds", {"event_ids": ",".join(fixture_ids)})
        return data.get("results", []), headers

    def get_best_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        data, headers = self._get("best-odds", {"event_ids": ",".join(fixture_ids)})
        return data.get("results", []), headers

    def get_live(self) -> tuple[list[dict], dict]:
        data, headers = self._get("events/live")
        return data.get("results", []), headers

    def get_standings(self, league_id: str, season_id: str) -> tuple[list[dict], dict]:
        data, headers = self._get("standings", {"league_id": league_id, "season_id": season_id})
        return data.get("results", []), headers

    def get_updated_since(self, resource: str, since_iso: str) -> tuple[list[dict], dict]:
        """Uses GoalDir's `updated_after` filter so we only pull rows that
        actually changed, instead of re-downloading everything."""
        data, headers = self._get(resource, {"updated_after": since_iso})
        return data.get("results", []), headers
