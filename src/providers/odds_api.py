"""
The Odds API client — used for independent market-price verification.

Verified against https://the-odds-api.com/liveapi/guides/v4/ (2026-09-25).

Key facts:
  - Host: https://api.the-odds-api.com  (IPv6: https://ipv6-api.the-odds-api.com)
  - Auth: apiKey is a query parameter, not a header
  - GET /v4/sports/{sport}/odds?regions=...&markets=...&apiKey=...
    cost = [markets specified] x [regions specified]
    e.g. markets=h2h,totals + regions=eu -> 2 credits
  - Response headers (always present): x-requests-remaining, x-requests-used,
    x-requests-last
  - 429 on burst; the docs say to space requests out over a few seconds
    rather than a documented Retry-After value
  - /v4/sports and /v4/sports/{sport}/events do NOT count against the quota
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
        clean_params = {k: v for k, v in params.items() if v is not None}
        clean_params["apiKey"] = self.api_key
        resp = requests.get(self.base_url + path, params=clean_params, timeout=20)

        if resp.status_code == 429:
            raise RateLimited(f"odds_api 429: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ProviderError(f"odds_api {resp.status_code}: {resp.text[:300]}")

        return resp.json(), dict(resp.headers)

    def get_sports(self, all_sports: bool = False) -> tuple[list[dict], dict]:
        """Does not count against the usage quota."""
        return self._get("sports/", {"all": "true" if all_sports else None})

    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        # The Odds API is odds-only; fixtures/results come from GoalDir/API-Football.
        return [], {}

    def get_events(self, sport_key: str, commence_time_from: str | None = None,
                    commence_time_to: str | None = None) -> tuple[list[dict], dict]:
        """GET /v4/sports/{sport}/events — event list with no odds, does not
        count against quota. Useful to get eventIds for the per-event-odds
        endpoint without spending credits."""
        data, headers = self._get(f"sports/{sport_key}/events", {
            "commenceTimeFrom": commence_time_from,
            "commenceTimeTo": commence_time_to,
        })
        return data, headers

    def get_odds(self, sport_key: str = "soccer_epl", markets: str = "h2h,totals",
                 regions: str = "eu", event_ids: str | None = None) -> tuple[list[dict], dict]:
        """GET /v4/sports/{sport}/odds — cost = len(markets) x len(regions).
        Keep `markets`/`regions` as narrow as the request actually needs;
        this is the #1 way this API's quota gets burned needlessly."""
        data, headers = self._get(f"sports/{sport_key}/odds", {
            "markets": markets,
            "regions": regions,
            "oddsFormat": "decimal",
            "eventIds": event_ids,
        })
        return data, headers

    def get_event_odds(self, sport_key: str, event_id: str, markets: str = "h2h,totals",
                        regions: str = "eu") -> tuple[dict, dict]:
        """GET /v4/sports/{sport}/events/{eventId}/odds — single event, same
        cost formula as /odds but only queries one game at a time."""
        return self._get(f"sports/{sport_key}/events/{event_id}/odds", {
            "markets": markets, "regions": regions, "oddsFormat": "decimal",
        })
