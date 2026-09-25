"""
Data validation / quarantine layer.

Nothing from a provider goes straight into the model. Every fixture and
odds record passes through here first; anything malformed is rejected
(and logged) rather than silently poisoning the historical DB — this is
the fix for the "league=other / date=null / duplicate rows" problems
described in the project notes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ValidationResult:
    ok: bool
    reasons: list = field(default_factory=list)


def validate_fixture(fx: dict) -> ValidationResult:
    reasons = []
    if not fx.get("home_team"):
        reasons.append("home_team missing")
    if not fx.get("away_team"):
        reasons.append("away_team missing")
    if fx.get("home_team") and fx.get("home_team") == fx.get("away_team"):
        reasons.append("home_team equals away_team")

    kickoff = fx.get("kickoff_utc")
    if not kickoff:
        reasons.append("kickoff missing")
    else:
        try:
            datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        except ValueError:
            reasons.append("kickoff invalid")

    league_id = fx.get("league_id")
    league_name = fx.get("league_name")
    if not league_id or not league_name or league_name.strip().lower() in ("", "other"):
        reasons.append("league identity incomplete (id/name)")

    season = fx.get("season_id")
    if season is None:
        reasons.append("season_id missing (never invent one from a calendar year)")

    score = fx.get("score")
    if score is not None:
        h, a = score.get("home"), score.get("away")
        if h is not None and (h < 0 or h > 20):
            reasons.append("impossible home score")
        if a is not None and (a < 0 or a > 20):
            reasons.append("impossible away score")

    return ValidationResult(ok=len(reasons) == 0, reasons=reasons)


def validate_odds(odds: dict) -> ValidationResult:
    reasons = []
    price = odds.get("price")
    if price is None or price <= 1.0:
        reasons.append("odds price missing or <= 1.0 (impossible)")
    if not odds.get("market"):
        reasons.append("market missing")
    if not odds.get("bookmaker"):
        reasons.append("bookmaker missing")
    return ValidationResult(ok=len(reasons) == 0, reasons=reasons)


def dedupe_events(events: list[dict], key_fields=("provider_event_id", "provider")) -> list[dict]:
    seen = set()
    out = []
    for e in events:
        key = tuple(e.get(f) for f in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def enforce_no_leakage(prediction_timestamp: str, feature_timestamps: list[str]) -> ValidationResult:
    """A feature dated after the prediction was made must never be used
    (e.g. a 20:05 lineup cannot feed a 19:00 prematch prediction)."""
    pt = datetime.fromisoformat(prediction_timestamp.replace("Z", "+00:00"))
    bad = [t for t in feature_timestamps if datetime.fromisoformat(t.replace("Z", "+00:00")) > pt]
    if bad:
        return ValidationResult(ok=False, reasons=[f"future data leaked into prediction: {bad}"])
    return ValidationResult(ok=True)
