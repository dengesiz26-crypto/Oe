"""
Per-provider rate limiting + persistent quota state.

Tracks daily / per-minute usage across GitHub Actions runs (state is
committed to data/state/quota.json between runs, since each Action run
starts a fresh container). Reads provider response headers where
available (The Odds API: x-requests-remaining/x-requests-used/x-requests-last;
API-Football: daily/per-minute remaining headers) so our local counters
stay in sync with the provider's own truth.
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from datetime import datetime, timezone


class RateLimiter:
    def __init__(self, state_path: str = "data/state/quota.json"):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except json.JSONDecodeError:
                pass
        return {}

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2, ensure_ascii=False))
        tmp.replace(self.state_path)

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _bucket(self, provider: str) -> dict:
        b = self._state.setdefault(provider, {})
        if b.get("date") != self._today():
            b["date"] = self._today()
            b["daily_used"] = 0
        b.setdefault("minute_used", 0)
        b.setdefault("minute_window_start", time.time())
        b.setdefault("consecutive_429", 0)
        b.setdefault("circuit_open_until", 0)
        return b

    def sync_from_headers(self, provider: str, headers: dict) -> None:
        """Reconcile local counters with a provider's own remaining-quota headers."""
        b = self._bucket(provider)
        lower = {k.lower(): v for k, v in headers.items()}
        for key in ("x-requests-remaining", "x-ratelimit-requests-remaining"):
            if key in lower:
                b["daily_remaining_reported"] = int(lower[key])
        for key in ("x-requests-used", "x-ratelimit-requests-used"):
            if key in lower:
                b["daily_used_reported"] = int(lower[key])
        self._save()

    def can_call(self, provider: str, daily_limit: int | None, minute_limit: int | None) -> bool:
        b = self._bucket(provider)
        if time.time() < b.get("circuit_open_until", 0):
            return False
        if time.time() - b["minute_window_start"] > 60:
            b["minute_window_start"] = time.time()
            b["minute_used"] = 0
        if daily_limit is not None and b["daily_used"] >= daily_limit:
            return False
        if minute_limit is not None and b["minute_used"] >= minute_limit:
            return False
        return True

    def quota_fraction_remaining(self, provider: str, daily_limit: int | None) -> float:
        if daily_limit is None:
            return 1.0
        b = self._bucket(provider)
        used = b.get("daily_used_reported", b["daily_used"])
        return max(0.0, (daily_limit - used) / daily_limit)

    def record_call(self, provider: str) -> None:
        b = self._bucket(provider)
        b["daily_used"] += 1
        b["minute_used"] += 1
        b["consecutive_429"] = 0
        self._save()

    def record_429(self, provider: str) -> float:
        """Record a rate-limit response and return the backoff (seconds) to wait
        before the next attempt. Exponential backoff + jitter; after enough
        consecutive 429s the circuit opens (provider paused) for a cooldown."""
        import random
        b = self._bucket(provider)
        b["consecutive_429"] += 1
        n = b["consecutive_429"]
        backoff = min(600, (2 ** n) + random.uniform(0, 1))
        if n >= 5:
            b["circuit_open_until"] = time.time() + 900  # pause provider 15 min
        self._save()
        return backoff

    def status(self, provider: str) -> dict:
        b = self._bucket(provider)
        return {
            "provider": provider,
            "daily_used": b["daily_used"],
            "minute_used": b["minute_used"],
            "consecutive_429": b["consecutive_429"],
            "circuit_open": time.time() < b.get("circuit_open_until", 0),
        }
