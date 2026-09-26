"""Shared interface every provider client implements.

Only get_fixtures is required — odds retrieval shapes differ enough between
providers (GoalDir: per-event consensus shortcut or a bulk feed; The Odds
API: market x region priced list; API-Football: per-fixture; SportAPI: none)
that forcing one get_odds(fixture_ids) signature would misrepresent all of
them. Each provider documents its own odds method(s) instead."""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        """Return (fixtures, response_headers)."""
