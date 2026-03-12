"""Probability helper functions for sportsbook odds."""

from __future__ import annotations

from typing import Tuple


def american_to_implied_prob(moneyline: int | float | None) -> float | None:
    """Convert an American moneyline into an implied win probability."""
    if moneyline is None:
        return None

    price = float(moneyline)
    if price == 0:
        return None

    if price > 0:
        return 100.0 / (price + 100.0)

    return abs(price) / (abs(price) + 100.0)


def no_vig_probs(
    home_implied_prob: float | None,
    away_implied_prob: float | None,
) -> Tuple[float | None, float | None]:
    """Remove the sportsbook vig by normalizing the two implied probabilities."""
    if home_implied_prob is None or away_implied_prob is None:
        return None, None

    total_prob = home_implied_prob + away_implied_prob
    if total_prob <= 0:
        return None, None

    return home_implied_prob / total_prob, away_implied_prob / total_prob
