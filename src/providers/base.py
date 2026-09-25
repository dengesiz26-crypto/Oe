"""Shared interface every provider client implements."""
from __future__ import annotations
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_fixtures(self, date_from: str, date_to: str) -> tuple[list[dict], dict]:
        """Return (fixtures, response_headers)."""

    @abstractmethod
    def get_odds(self, fixture_ids: list[str]) -> tuple[list[dict], dict]:
        """Return (odds_records, response_headers)."""
