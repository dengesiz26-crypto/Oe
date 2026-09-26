"""
Independent-Poisson goal model.

Given each team's attack/defence strength (derived from goals for/against,
adjusted for opponent & home advantage), we get expected goals (lambda) for
each side, then read off 1X2 and Over/Under probabilities from the Poisson
distribution — this is the classic Maher (1982) baseline the rest of the
engine (Dixon-Coles correction, Elo blend) builds on.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


@dataclass
class TeamStrength:
    attack: float   # goals-scored rate relative to league average (1.0 = average)
    defence: float  # goals-conceded rate relative to league average (1.0 = average)


def expected_goals(home: TeamStrength, away: TeamStrength,
                    league_avg_home_goals: float = 1.5,
                    league_avg_away_goals: float = 1.15) -> tuple[float, float]:
    lambda_home = home.attack * away.defence * league_avg_home_goals
    lambda_away = away.attack * home.defence * league_avg_away_goals
    return max(lambda_home, 0.05), max(lambda_away, 0.05)


def score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 10) -> list[list[float]]:
    return [[_poisson_pmf(h, lambda_home) * _poisson_pmf(a, lambda_away)
             for a in range(max_goals + 1)] for h in range(max_goals + 1)]


def market_probabilities(matrix: list[list[float]]) -> dict:
    n = len(matrix)
    p_home = p_draw = p_away = 0.0
    over_under = {}
    btts_yes = 0.0
    home_goals_dist = [0.0] * n
    away_goals_dist = [0.0] * n

    for h in range(n):
        for a in range(n):
            p = matrix[h][a]
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
            if h > 0 and a > 0:
                btts_yes += p
            home_goals_dist[h] += p
            away_goals_dist[a] += p

    for line in (0.5, 1.5, 2.5, 3.5):
        over = sum(matrix[h][a] for h in range(n) for a in range(n) if h + a > line)
        over_under[line] = {"over": over, "under": 1 - over}

    def team_over(dist: list[float], line: float) -> float:
        cutoff = int(line)  # e.g. line 1.5 -> goals > 1.5 means goals >= 2
        return sum(v for i, v in enumerate(dist) if i > cutoff)

    return {
        "1x2": {"home": p_home, "draw": p_draw, "away": p_away},
        "over_under": over_under,
        "btts": {"yes": btts_yes, "no": 1 - btts_yes},
        "home_team_over": {line: team_over(home_goals_dist, line) for line in (0.5, 1.5, 2.5)},
        "away_team_over": {line: team_over(away_goals_dist, line) for line in (0.5, 1.5, 2.5)},
    }
