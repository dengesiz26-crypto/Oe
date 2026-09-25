"""
The Odds API client — used for independent market-price verification.

Base URL: https://api.the-odds-api.com/v4/
Cost model: a single /odds call costs (markets requested) x (regions
requested) credits, e.g. h2h+totals in one region = 2 credits. We keep
markets/regions as small as the request actually needs and read the
quota back from response headers (x-requests-remaining, x-requests-used,
x-requests-last) via ApiManager -> RateLimiter.sync_from_headers.
"""
from __future__ import annotations
from src.providers.base import BaseProvider
from src.core.api_manager import RateLimited, ProviderError
from src.core.config import settings


class OddsApiProvider(BaseProvider):
    name = "odds_api"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or settings.odds_api_key
        self.base_url = base_url or settings.odds_api_base_url

    def _get(self, path: str, params: dict) -> tuple[dict, dict]:
        if not self.api_key:
            raise ProviderError("ODDS_API_KEY not set")
        import requests
        params = {**params, "apiKey": self.api_key}
        resp = requests.get(self.base_url + path, params=params, timeout=20)
        if resp.status_code == 429:
            raise RateLimited("odds_api 429")
        if resp.status_code >= 400:
            raise ProviderError(f"odds_api {resp.status_code}: {resp.text[:200]}")
        return resp.json(), dict(resp.headers)

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        # The Odds API is odds-only; fixtures come from GoalDir/API-Football.
        return [], {}

    def get_odds(self, sport_key: str = "soccer_epl", markets: str = "h2h,totals",
                 regions: str = "eu") -> tuple[list[dict], dict]:
        data, headers = self._get(f"sports/{sport_key}/odds", {
            "markets": markets,
            "regions": regions,
            "oddsFormat": "decimal",
        })
        return data, headers
