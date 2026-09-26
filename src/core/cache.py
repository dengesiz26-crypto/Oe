"""
Simple, dependency-free JSON file cache with per-key TTL.

Design goal: never call a provider for data we already have and that is
still "fresh enough" per the provider's documented refresh cadence
(e.g. GoalDir odds ~3min, best-odds ~5min; league lists ~24h; etc).
"""
from __future__ import annotations
import json
import time
import hashlib
import os
from pathlib import Path
from typing import Any, Optional


class Cache:
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:24]
        safe = "".join(c for c in key if c.isalnum() or c in "-_")[:60]
        return self.cache_dir / f"{safe}__{h}.json"

    def get(self, key: str) -> Optional[Any]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                envelope = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() > envelope["expires_at"]:
            return None
        return envelope["value"]

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        envelope = {
            "key": key,
            "cached_at": time.time(),
            "expires_at": time.time() + ttl_seconds,
            "value": value,
        }
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(envelope, f, ensure_ascii=False)
        os.replace(tmp, p)

    def is_fresh(self, key: str) -> bool:
        return self.get(key) is not None
