"""
Risk + decision classification.

Combines probability band (BANKO/STANDARD/IDEAL/RISKLI/UZAK DUR) with a
composite risk_score from data completeness, model disagreement, league
reliability, market calibration history, and form volatility — then
applies the MIN_ODDS / value gate to produce a final PLAY / NO BET
decision. A "BANKO" probability read and a "PLAY" betting decision are
two different things by design (spec section 1, 13, 34).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from src.core.config import settings
from src.engine.value_engine import ValueResult


@dataclass
class RiskInputs:
    data_completeness: float = 1.0       # 0..1, fraction of expected fields present
    model_disagreement: float = 0.0      # 0..1, spread between Poisson/Elo blend components
    league_reliability: float = 1.0      # 0..1, historical calibration quality for this league
    market_calibration_error: float = 0.0  # 0..1, ECE for this probability bucket/market
    form_volatility: float = 0.0         # 0..1, recent results volatility


@dataclass
class RiskResult:
    classification: str   # BANKO | STANDARD | IDEAL | RISKLI | UZAK DUR
    risk_level: str        # LOW | MEDIUM | HIGH
    decision: str           # PLAY | NO BET
    risk_score: float
    notes: list = field(default_factory=list)


def classify_probability(probability: float) -> str:
    bands = settings.classification_bands
    if probability >= bands["BANKO"]:
        return "BANKO"
    if probability >= bands["STANDARD"]:
        return "STANDARD"
    if probability >= bands["IDEAL"]:
        return "IDEAL"
    if probability >= bands["RISKLI"]:
        return "RISKLI"
    return "UZAK DUR"


def compute_risk_score(inputs: RiskInputs) -> float:
    # weighted composite, 0 (safest) .. 1 (riskiest) — weights are a
    # starting point to be tuned once enough settled episodes exist
    score = (
        0.30 * (1 - inputs.data_completeness) +
        0.25 * inputs.model_disagreement +
        0.20 * (1 - inputs.league_reliability) +
        0.15 * inputs.market_calibration_error +
        0.10 * inputs.form_volatility
    )
    return round(min(max(score, 0.0), 1.0), 4)


def evaluate(probability: float, value: ValueResult, risk_inputs: RiskInputs) -> RiskResult:
    classification = classify_probability(probability)
    risk_score = compute_risk_score(risk_inputs)
    risk_level = "LOW" if risk_score < 0.3 else "MEDIUM" if risk_score < 0.6 else "HIGH"

    notes = []
    decision = "PLAY"

    if not value.meets_min_odds:
        decision = "NO BET"
        notes.append(f"odds below MIN_ODDS floor ({settings.min_odds})")
    if not value.has_positive_edge:
        decision = "NO BET"
        notes.append("no positive edge vs market price")
    if risk_level == "HIGH":
        decision = "NO BET"
        notes.append("composite risk score too high")
    if classification == "UZAK DUR":
        decision = "NO BET"
        notes.append("probability below minimum confidence band")

    return RiskResult(
        classification=classification,
        risk_level=risk_level,
        decision=decision,
        risk_score=risk_score,
        notes=notes,
    )
