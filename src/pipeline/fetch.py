"""
Fetch stage: pulls only what's actually needed (incremental, cache-aware,
priority-tagged) through the ApiManager rather than re-downloading
everything on every run (spec section 8-9).
"""
from __future__ import annotations
from src.core.api_manager import ApiManager, ApiRequest, PRIORITY_PREDICTION, PRIORITY_CRITICAL
from src.providers.goaldir import GoalDirProvider
from src.core.config import settings


def fetch_upcoming_fixtures(manager: ApiManager, date_from: str, date_to: str) -> list[dict]:
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key=f"goaldir:fixtures:{date_from}:{date_to}",
        fetch_fn=lambda: provider.get_fixtures(date_from, date_to),
        priority=PRIORITY_PREDICTION,
    )
    return manager.request(req) or []


def fetch_finished_fixtures(manager: ApiManager, date_from: str, date_to: str) -> list[dict]:
    provider = GoalDirProvider()
    req = ApiRequest(
        provider="goaldir",
        cache_key=f"goaldir:finished:{date_from}:{date_to}",
        fetch_fn=lambda: provider.get_fixtures(date_from, date_to),
        priority=PRIORITY_CRITICAL,  # result settlement is P0
        force_refresh=True,
    )
    return manager.request(req) or []
