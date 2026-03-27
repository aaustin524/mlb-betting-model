"""Small CLI to verify weather and MLB stat inputs in the local pipeline."""

from __future__ import annotations

import argparse
import sqlite3
from typing import Iterable

import pandas as pd

from app.runtime_env import resolve_database_path
from model.weather_api import get_weather_for_team, load_stadium_locations

CORE_TABLES = [
    "games",
    "teams",
    "starting_pitchers",
    "team_daily_stats",
    "pitcher_daily_stats",
    "model_features",
    "predictions",
]
FEATURE_COLUMNS_TO_CHECK = [
    "home_win_pct_last10",
    "away_win_pct_last10",
    "home_runs_per_game_last14",
    "away_runs_per_game_last14",
    "home_starter_era",
    "away_starter_era",
    "home_starter_fip",
    "away_starter_fip",
    "home_bullpen_ip_last3",
    "away_bullpen_ip_last3",
]


def build_parser() -> argparse.ArgumentParser:
    """Create command-line args for quick verification."""
    parser = argparse.ArgumentParser(
        description="Verify whether weather and MLB stats are loaded into the model pipeline."
    )
    parser.add_argument(
        "--team",
        default="New York Yankees",
        help="Home team name to use for the weather check.",
    )
    parser.add_argument(
        "--weather-mode",
        default="local",
        choices=["local", "live"],
        help="Weather mode to test. 'local' uses defaults, 'live' calls the NWS path.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=5,
        help="How many sample rows to print for recent games and model features.",
    )
    return parser


def fetch_table_counts(connection: sqlite3.Connection, tables: Iterable[str]) -> list[tuple[str, int]]:
    """Return row counts for a small list of tables."""
    counts: list[tuple[str, int]] = []
    for table_name in tables:
        row_count = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        counts.append((table_name, int(row_count)))
    return counts


def print_table_counts(connection: sqlite3.Connection) -> None:
    """Print a compact summary of the main pipeline tables."""
    print("Table counts")
    for table_name, row_count in fetch_table_counts(connection, CORE_TABLES):
        print(f"  {table_name}: {row_count}")


def print_recent_games(connection: sqlite3.Connection, sample_limit: int) -> None:
    """Show recent games so it is obvious whether MLB schedule/results data exists."""
    query = """
        SELECT
            game_id,
            game_date,
            home_team_id,
            away_team_id,
            home_score,
            away_score
        FROM games
        ORDER BY game_date DESC, game_id DESC
        LIMIT ?
    """
    games_df = pd.read_sql_query(query, connection, params=(sample_limit,))

    print("\nRecent games")
    if games_df.empty:
        print("  No rows found in games.")
        return

    print(games_df.to_string(index=False))


def print_feature_health(connection: sqlite3.Connection, sample_limit: int) -> None:
    """Show whether model features exist and whether core fields are populated."""
    total_features = connection.execute("SELECT COUNT(*) FROM model_features").fetchone()[0]
    print("\nModel feature health")
    print(f"  model_features rows: {total_features}")

    if total_features == 0:
        print("  No feature rows found yet.")
        return

    completeness_parts: list[str] = []
    for column_name in FEATURE_COLUMNS_TO_CHECK:
        non_null_count = connection.execute(
            f"SELECT COUNT(*) FROM model_features WHERE {column_name} IS NOT NULL"
        ).fetchone()[0]
        completeness_parts.append(f"{column_name}={non_null_count}/{total_features}")

    print("  Non-null coverage:")
    for part in completeness_parts:
        print(f"    {part}")

    sample_query = f"""
        SELECT
            game_id,
            home_win_pct_last10,
            away_win_pct_last10,
            home_starter_era,
            away_starter_era,
            home_starter_fip,
            away_starter_fip
        FROM model_features
        ORDER BY game_id DESC
        LIMIT {int(sample_limit)}
    """
    sample_df = pd.read_sql_query(sample_query, connection)
    print("\nFeature sample")
    print(sample_df.to_string(index=False))


def print_weather_check(team: str, weather_mode: str) -> None:
    """Call the weather helper directly and show which source responded."""
    stadium_locations = load_stadium_locations()
    weather_snapshot = get_weather_for_team(
        home_team=team,
        stadium_df=stadium_locations,
        data_mode=weather_mode,
    )

    print("\nWeather check")
    print(f"  team: {team}")
    print(f"  requested_mode: {weather_mode}")
    print(f"  source: {weather_snapshot.get('weather_source')}")
    print(f"  temperature_f: {weather_snapshot.get('temperature_f')}")
    print(f"  wind_factor: {weather_snapshot.get('wind_factor')}")


def print_verdicts(connection: sqlite3.Connection) -> None:
    """Print beginner-friendly takeaways from the current DB state."""
    team_stats_count = connection.execute("SELECT COUNT(*) FROM team_daily_stats").fetchone()[0]
    pitcher_stats_count = connection.execute("SELECT COUNT(*) FROM pitcher_daily_stats").fetchone()[0]
    starter_count = connection.execute("SELECT COUNT(*) FROM starting_pitchers").fetchone()[0]
    feature_count = connection.execute("SELECT COUNT(*) FROM model_features").fetchone()[0]

    print("\nQuick verdict")
    if team_stats_count == 0 and pitcher_stats_count == 0:
        print("  MLB team and pitcher stat tables are empty right now.")
    else:
        print("  MLB stat tables contain data, so the feature builder has inputs available.")

    if starter_count == 0:
        print("  Starting pitcher rows are empty, so starter ERA/FIP features cannot populate yet.")

    if feature_count == 0:
        print("  model_features is empty, so the model has not been fed engineered game rows yet.")


def main() -> None:
    """Run all verification checks."""
    args = build_parser().parse_args()
    db_path = resolve_database_path()

    print(f"Database path: {db_path}")
    with sqlite3.connect(db_path) as connection:
        print_table_counts(connection)
        print_recent_games(connection, sample_limit=args.sample_limit)
        print_feature_health(connection, sample_limit=args.sample_limit)
        print_verdicts(connection)

    print_weather_check(team=args.team, weather_mode=args.weather_mode)


if __name__ == "__main__":
    main()
