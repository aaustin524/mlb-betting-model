from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from project_config import (
    DB_PATH,
    DEFAULT_BASELINE_RUNS_PER_GAME,
    DEFAULT_ENVIRONMENT_BLEND_WEIGHT,
    DEFAULT_LOOKBACK_GAMES,
)


def load_recent_completed_games(
    db_path: str | Path = DB_PATH,
    lookback_games: int = DEFAULT_LOOKBACK_GAMES,
) -> pd.DataFrame:
    db_path = Path(db_path)
    if not db_path.exists():
        return pd.DataFrame(columns=["home_score", "away_score"])

    query = """
        SELECT
            game_date,
            home_score,
            away_score
        FROM games
        WHERE home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY game_date DESC, game_id DESC
        LIMIT ?
    """

    with sqlite3.connect(db_path) as connection:
        games_df = pd.read_sql_query(query, connection, params=[int(lookback_games)])

    if games_df.empty:
        return games_df

    games_df["home_score"] = pd.to_numeric(games_df["home_score"], errors="coerce")
    games_df["away_score"] = pd.to_numeric(games_df["away_score"], errors="coerce")
    games_df = games_df.dropna(subset=["home_score", "away_score"])
    return games_df


def get_run_environment_factor(
    db_path: str | Path = DB_PATH,
    lookback_games: int = DEFAULT_LOOKBACK_GAMES,
    baseline_runs_per_game: float = DEFAULT_BASELINE_RUNS_PER_GAME,
    blend_weight: float = DEFAULT_ENVIRONMENT_BLEND_WEIGHT,
) -> float:
    """
    Estimate a lightweight league scoring calibration factor.

    League scoring drifts over time because baseball changes: run ball environments,
    roster construction, strike-zone enforcement, bullpen usage, and injuries all
    move the scoring climate. A small league-level correction helps totals and side
    accuracy because it nudges every matchup toward the current run environment.

    The factor is blended back toward 1.00 so it does not overreact to short-term
    noise in recent scores.
    """
    if baseline_runs_per_game <= 0:
        raise ValueError("baseline_runs_per_game must be greater than 0")
    if blend_weight < 0:
        raise ValueError("blend_weight must be non-negative")

    recent_games = load_recent_completed_games(db_path=db_path, lookback_games=lookback_games)
    if recent_games.empty:
        return 1.0

    recent_runs_per_game = (recent_games["home_score"] + recent_games["away_score"]).mean()
    if pd.isna(recent_runs_per_game) or recent_runs_per_game <= 0:
        return 1.0

    raw_factor = float(recent_runs_per_game) / float(baseline_runs_per_game)
    return round((1.0 * (1.0 - blend_weight)) + (raw_factor * blend_weight), 3)
