"""
API Manager — the single gateway every provider call goes through.

Responsibilities (per project spec section 6-8, 26-28):
  - cache-first (never re-fetch data that's still fresh)
  - quota + rate limit enforcement (daily/minute, per provider)
  - priority queue (P0 critical .. P4 research) — low priority calls are
    the first to be skipped when quota runs low
  - retry with exponential backoff + jitter on 429s, circuit breaker after
    repeated failures
  - structured status reporting: {provider, daily_remaining, next_allowed_at, status}
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Callable, Optional

from src.core.cache import Cache
from src.core.rate_limiter import RateLimiter
from src.core.config import settings, ProviderLimits


PRIORITY_CRITICAL = 0   # result settlement
PRIORITY_PREDICTION = 1  # new fixture / prematch data
PRIORITY_LIVE = 2
PRIORITY_ENRICHMENT = 3  # H2H, secondary validation
PRIORITY_RESEARCH = 4    # nice-to-have extra data


@dataclass
class ApiRequest:
    provider: str
    cache_key: str
    fetch_fn: Callable[[], tuple]  # returns (payload, response_headers)
    priority: int = PRIORITY_ENRICHMENT
    force_refresh: bool = False


class ApiManager:
    def __init__(self, cache: Optional[Cache] = None, limiter: Optional[RateLimiter] = None):
        self.cache = cache or Cache(settings.data_dir + "/cache")
        self.limiter = limiter or RateLimiter(settings.data_dir + "/state/quota.json")

    def _limits(self, provider: str) -> ProviderLimits:
        return settings.provider_limits.get(provider, ProviderLimits())

    def request(self, req: ApiRequest, max_retries: int = 3):
        limits = self._limits(req.provider)

        # 1. cache first
        if not req.force_refresh:
            cached = self.cache.get(req.cache_key)
            if cached is not None:
                return cached

        # 2. quota pressure -> drop low priority requests
        remaining_frac = self.limiter.quota_fraction_remaining(req.provider, limits.daily_limit)
        if remaining_frac < settings.quota_safety_threshold and req.priority >= PRIORITY_ENRICHMENT:
            return None  # skip non-critical work to protect quota

        # 3. rate limit + retry loop
        attempt = 0
        while attempt <= max_retries:
            if not self.limiter.can_call(req.provider, limits.daily_limit, limits.minute_limit):
                return None  # respect quota/circuit breaker rather than spin

            try:
                payload, headers = req.fetch_fn()
            except RateLimited:
                wait = self.limiter.record_429(req.provider)
                time.sleep(min(wait, 2))  # capped sleep in this environment
                attempt += 1
                continue
            except ProviderError:
                attempt += 1
                time.sleep(min(2 ** attempt, 10))
                continue

            self.limiter.record_call(req.provider)
            if headers:
                self.limiter.sync_from_headers(req.provider, headers)
            self.cache.set(req.cache_key, payload, limits.cache_ttl_seconds)
            return payload

        return None  # exhausted retries; caller should fall back gracefully

    def provider_status(self) -> list[dict]:
        return [self.limiter.status(p) for p in settings.provider_limits]


class RateLimited(Exception):
    """Raised by a provider client on HTTP 429."""


class ProviderError(Exception):
    """Raised by a provider client on any other failure (timeout, 5xx, bad payload)."""
