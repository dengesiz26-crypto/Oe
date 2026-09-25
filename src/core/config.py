"""
Central configuration. All real secrets come from environment variables
(GitHub Actions secrets in production, .env locally) — nothing is hardcoded.
"""
import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


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
    goaldir_base_url: str = "https://sports.bzzoiro.com/api/v2/"

    odds_api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    odds_api_base_url: str = "https://api.the-odds-api.com/v4/"

    api_football_key: str = field(default_factory=lambda: os.environ.get("API_FOOTBALL_KEY", ""))
    api_football_base_url: str = "https://v3.football.api-sports.io/"

    sportapi_key: str = field(default_factory=lambda: os.environ.get("SPORTAPI_KEY", ""))
    sportapi_base_url: str = "https://sportapi.ai/"

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
    provider_limits: dict = field(default_factory=lambda: {
        "goaldir": ProviderLimits(daily_limit=None, minute_limit=None, cache_ttl_seconds=3 * 60, priority=1),
        "odds_api": ProviderLimits(daily_limit=500, minute_limit=None, cache_ttl_seconds=5 * 60, priority=1),
        "api_football": ProviderLimits(daily_limit=100, minute_limit=10, cache_ttl_seconds=6 * 3600, priority=3),
        "sportapi": ProviderLimits(daily_limit=None, minute_limit=None, cache_ttl_seconds=6 * 3600, priority=3),
    })

    data_dir: str = "data"
    docs_data_dir: str = "docs/data"


settings = Settings()
