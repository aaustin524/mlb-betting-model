"""Build beginner-friendly game features from historical results in SQLite."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from typing import Any

import pandas as pd

from app.config import DB_PATH
from app.db.schema import initialize_database

LOGGER = logging.getLogger(__name__)
V1_FEATURE_COLUMNS = [
    "home_win_pct_last10",
    "away_win_pct_last10",
    "home_runs_per_game_last14",
    "away_runs_per_game_last14",
    "home_runs_allowed_last14",
    "away_runs_allowed_last14",
    "home_field_flag",
    "target_home_win",
]


def build_parser() -> argparse.ArgumentParser:
    """Create a small command-line parser for feature building."""
    parser = argparse.ArgumentParser(
        description="Build model_features rows from historical games in SQLite."
    )
    parser.add_argument(
        "--start-date",
        help="Optional start date filter in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        help="Optional end date filter in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level for the script.",
    )
    return parser


def configure_logging(log_level: str) -> None:
    """Configure simple console logging."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_games(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load completed games with scores from the database."""
    query = """
        SELECT
            game_id,
            game_date,
            home_team_id,
            away_team_id,
            home_score,
            away_score
        FROM games
        WHERE home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY game_date, game_id
    """
    games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return games_df

    games_df["game_date"] = pd.to_datetime(games_df["game_date"])
    LOGGER.info("Loaded %s completed games from the games table", len(games_df))
    return games_df


def build_team_history(games_df: pd.DataFrame) -> pd.DataFrame:
    """Create one team-level result row for each side of every game."""
    home_history = games_df[["game_id", "game_date", "home_team_id", "home_score", "away_score"]].copy()
    home_history = home_history.rename(
        columns={
            "home_team_id": "team_id",
            "home_score": "runs_scored",
            "away_score": "runs_allowed",
        }
    )
    home_history["win"] = (home_history["runs_scored"] > home_history["runs_allowed"]).astype(int)

    away_history = games_df[["game_id", "game_date", "away_team_id", "away_score", "home_score"]].copy()
    away_history = away_history.rename(
        columns={
            "away_team_id": "team_id",
            "away_score": "runs_scored",
            "home_score": "runs_allowed",
        }
    )
    away_history["win"] = (away_history["runs_scored"] > away_history["runs_allowed"]).astype(int)

    team_history = pd.concat([home_history, away_history], ignore_index=True)
    return team_history.sort_values(["team_id", "game_date", "game_id"]).reset_index(drop=True)


def mean_or_none(values: pd.Series) -> float | None:
    """Return the mean as a float, or None when there is no history yet."""
    if values.empty:
        return None
    return float(values.mean())


def build_feature_row(game_row: pd.Series, team_history: pd.DataFrame) -> dict[str, Any]:
    """Build one model_features row using only games before the current game date."""
    game_date = game_row["game_date"]

    home_history = team_history[
        (team_history["team_id"] == game_row["home_team_id"])
        & (team_history["game_date"] < game_date)
    ]
    away_history = team_history[
        (team_history["team_id"] == game_row["away_team_id"])
        & (team_history["game_date"] < game_date)
    ]

    home_last10 = home_history.tail(10)
    away_last10 = away_history.tail(10)
    home_last14 = home_history.tail(14)
    away_last14 = away_history.tail(14)

    return {
        "game_id": int(game_row["game_id"]),
        "home_win_pct_last10": mean_or_none(home_last10["win"]),
        "away_win_pct_last10": mean_or_none(away_last10["win"]),
        "home_runs_per_game_last14": mean_or_none(home_last14["runs_scored"]),
        "away_runs_per_game_last14": mean_or_none(away_last14["runs_scored"]),
        "home_runs_allowed_last14": mean_or_none(home_last14["runs_allowed"]),
        "away_runs_allowed_last14": mean_or_none(away_last14["runs_allowed"]),
        "home_field_flag": 1,
        "target_home_win": 1 if game_row["home_score"] > game_row["away_score"] else 0,
    }


def filter_games(games_df: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    """Apply optional date filters after all history has been loaded."""
    filtered_df = games_df

    if start_date:
        filtered_df = filtered_df[filtered_df["game_date"] >= pd.to_datetime(start_date)]

    if end_date:
        filtered_df = filtered_df[filtered_df["game_date"] <= pd.to_datetime(end_date)]

    return filtered_df.sort_values(["game_date", "game_id"]).reset_index(drop=True)


def upsert_model_features(connection: sqlite3.Connection, feature_rows: list[dict[str, Any]]) -> int:
    """Insert or update model feature rows without creating duplicates."""
    if not feature_rows:
        return 0

    connection.executemany(
        """
        INSERT INTO model_features (
            game_id,
            home_win_pct_last10,
            away_win_pct_last10,
            home_runs_per_game_last14,
            away_runs_per_game_last14,
            home_runs_allowed_last14,
            away_runs_allowed_last14,
            home_field_flag,
            target_home_win
        )
        VALUES (
            :game_id,
            :home_win_pct_last10,
            :away_win_pct_last10,
            :home_runs_per_game_last14,
            :away_runs_per_game_last14,
            :home_runs_allowed_last14,
            :away_runs_allowed_last14,
            :home_field_flag,
            :target_home_win
        )
        ON CONFLICT(game_id) DO UPDATE SET
            home_win_pct_last10 = excluded.home_win_pct_last10,
            away_win_pct_last10 = excluded.away_win_pct_last10,
            home_runs_per_game_last14 = excluded.home_runs_per_game_last14,
            away_runs_per_game_last14 = excluded.away_runs_per_game_last14,
            home_runs_allowed_last14 = excluded.home_runs_allowed_last14,
            away_runs_allowed_last14 = excluded.away_runs_allowed_last14,
            home_field_flag = excluded.home_field_flag,
            target_home_win = excluded.target_home_win
        """,
        feature_rows,
    )
    connection.commit()
    return len(feature_rows)


def build_game_features(start_date: str | None = None, end_date: str | None = None) -> int:
    """Build one model_features row per game using only prior-game history."""
    initialize_database()

    with sqlite3.connect(DB_PATH) as connection:
        games_df = load_games(connection)

        if games_df.empty:
            LOGGER.warning("No completed games with scores were found in the games table.")
            return 0

        team_history = build_team_history(games_df)
        games_to_process = filter_games(games_df, start_date, end_date)

        LOGGER.info("Building v1 features for %s games", len(games_to_process))

        feature_rows: list[dict[str, Any]] = []
        for _, game_row in games_to_process.iterrows():
            feature_rows.append(build_feature_row(game_row, team_history))

        upserted_count = upsert_model_features(connection, feature_rows)
        LOGGER.info("Upserted %s model_features rows", upserted_count)
        return upserted_count


def main() -> None:
    """Run the feature builder from the command line."""
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    upserted_count = build_game_features(
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(f"Built {upserted_count} model_features rows in {DB_PATH}")


if __name__ == "__main__":
    main()
