"""
Football Elo rating system with home advantage and goal-difference margin
multiplier (as used by e.g. eloratings.net for national teams, adapted
for club football). Used as an independent signal that is blended with
the Poisson/Dixon-Coles goal model rather than replacing it.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field


@dataclass
class EloState:
    ratings: dict = field(default_factory=dict)
    k_factor: float = 20.0
    home_advantage: float = 60.0

    def get(self, team: str) -> float:
        return self.ratings.get(team, 1500.0)

    def win_probability(self, home_team: str, away_team: str) -> dict:
        diff = (self.get(home_team) + self.home_advantage) - self.get(away_team)
        p_home_or_draw_split = 1 / (1 + 10 ** (-diff / 400))
        # crude 1X2 split derived from the win-expectancy curve; the
        # probability engine blends this with the Poisson result rather
        # than using it standalone.
        p_home = p_home_or_draw_split ** 1.4
        p_away = (1 - p_home_or_draw_split) ** 1.4
        p_draw = max(0.0, 1 - p_home - p_away)
        norm = p_home + p_draw + p_away
        return {"home": p_home / norm, "draw": p_draw / norm, "away": p_away / norm}

    def update(self, home_team: str, away_team: str, home_goals: int, away_goals: int) -> None:
        r_home, r_away = self.get(home_team), self.get(away_team)
        expected_home = 1 / (1 + 10 ** (-((r_home + self.home_advantage) - r_away) / 400))
        if home_goals > away_goals:
            actual_home = 1.0
        elif home_goals == away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0

        gd = abs(home_goals - away_goals)
        margin_mult = math.log(max(gd, 1) + 1) * (2.2 / ((abs(r_home - r_away) * 0.001) + 2.2))

        delta = self.k_factor * margin_mult * (actual_home - expected_home)
        self.ratings[home_team] = r_home + delta
        self.ratings[away_team] = r_away - delta
