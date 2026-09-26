"""
Central configuration. All real secrets come from environment variables
(GitHub Actions secrets in production, .env locally) — nothing is hardcoded.

Base URLs and rate-limit numbers below are taken from each provider's own
published docs (checked 2026-09-25):
  - GoalDir/BSD:     https://goaldir.com/docs/football/  +  /docs/conventions/
  - The Odds API:    https://the-odds-api.com/liveapi/guides/v4/
  - API-Football:    https://www.api-football.com/documentation-v3
  - SportAPI.ai:      https://sportapi.ai/docs
"""
import os
from dataclasses import dataclass, field


@dataclass
class ProviderLimits:
    daily_limit: int | None = None
    minute_limit: int | None = None
    cache_ttl_seconds: int = 3600
    priority: int = 2  # P0=critical ... P4=research


@dataclass
class Settings:
    # --- API credentials (read from env, never committed) ---
    goaldir_api_key: str = field(default_factory=lambda: os.environ.get("GOALDIR_API_KEY", ""))
    # Football v2 base path, per https://goaldir.com/docs/football/ and /docs/conventions/
    goaldir_base_url: str = "https://sports.bzzoiro.com/api/v2/"

    odds_api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    odds_api_base_url: str = "https://api.the-odds-api.com/v4/"

    api_football_key: str = field(default_factory=lambda: os.environ.get("API_FOOTBALL_KEY", ""))
    # Direct API-Sports host (x-apisports-key auth). If the key was issued via
    # RapidAPI instead, set API_FOOTBALL_VIA_RAPIDAPI=1 and the client switches
    # to api-football-v1.p.rapidapi.com with x-rapidapi-key/x-rapidapi-host.
    api_football_base_url: str = "https://v3.football.api-sports.io/"
    api_football_via_rapidapi: bool = field(
        default_factory=lambda: os.environ.get("API_FOOTBALL_VIA_RAPIDAPI", "") == "1"
    )

    sportapi_key: str = field(default_factory=lambda: os.environ.get("SPORTAPI_KEY", ""))
    # Real base path is /api under the sportapi.ai host — NOT the bare domain.
    sportapi_base_url: str = "https://sportapi.ai/api/"

    # --- decision thresholds (tune later via calibration/backtest) ---
    min_odds: float = 1.25
    quota_safety_threshold: float = 0.15  # stop non-critical calls below 15% quota remaining

    classification_bands: dict = field(default_factory=lambda: {
        "BANKO": 0.65,
        "STANDARD": 0.60,
        "IDEAL": 0.55,
        "RISKLI": 0.48,
        # below RISKLI floor -> "UZAK DUR"
    })

    # --- per-provider quota/cache/priority config ---
    # goaldir: 7,500 req/day free tier since 2026-08-17 (per /docs/conventions/),
    #          plus a 25 req/s burst cap we don't model per-minute here since our
    #          own polling is nowhere near that fast.
    # odds_api: quota is plan-dependent; 500 is a conservative default for the
    #          free/starter tier — override by reading real remaining quota from
    #          response headers once the first live call has run.
    # api_football: free plan is 100 req/day, 10 req/min.
    provider_limits: dict = field(default_factory=lambda: {
        "goaldir": ProviderLimits(daily_limit=7500, minute_limit=None, cache_ttl_seconds=3 * 60, priority=1),
        "odds_api": ProviderLimits(daily_limit=500, minute_limit=None, cache_ttl_seconds=5 * 60, priority=1),
        "api_football": ProviderLimits(daily_limit=100, minute_limit=10, cache_ttl_seconds=6 * 3600, priority=3),
        "sportapi": ProviderLimits(daily_limit=None, minute_limit=None, cache_ttl_seconds=6 * 3600, priority=3),
    })

    data_dir: str = "data"
    docs_data_dir: str = "docs/data"


settings = Settings()
