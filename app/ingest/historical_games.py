"""Load historical and upcoming MLB schedule rows from the MLB Stats API."""

from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import Any

import requests

from app.db.connection import get_connection
from app.db.schema import initialize_database

LOGGER = logging.getLogger(__name__)
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
DEFAULT_GAME_TYPE = "R"


def build_parser() -> argparse.ArgumentParser:
    """Create a beginner-friendly CLI parser."""
    parser = argparse.ArgumentParser(
        description="Load MLB schedule rows into SQLite, including upcoming scheduled games.",
    )
    parser.add_argument("--season", type=int, help="Optional MLB season to load.")
    parser.add_argument("--start-date", help="Optional start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="Optional end date in YYYY-MM-DD format.")
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


def fetch_schedule(
    season: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch MLB schedule groups from the Stats API."""
    params: dict[str, Any] = {
        "sportId": 1,
        "gameType": DEFAULT_GAME_TYPE,
        "hydrate": "probablePitcher",
    }
    if season is not None:
        params["season"] = season
    if start_date:
        params["startDate"] = start_date
    if end_date:
        params["endDate"] = end_date

    response = requests.get(SCHEDULE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("dates", [])


def parse_schedule_rows(
    dates: list[dict[str, Any]],
    season: int | None = None,
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, int | None, str]], list[tuple[Any, ...]]]:
    """Normalize API payload into team, pitcher, and game rows."""
    team_rows: dict[int, tuple[int, str, str]] = {}
    pitcher_rows: dict[int, tuple[int, str, int | None, str]] = {}
    game_rows: list[tuple[Any, ...]] = []

    for day in dates:
        game_date = str(day.get("date"))
        for game in day.get("games", []):
            game_pk = game.get("gamePk")
            if game_pk is None:
                continue

            status_data = game.get("status", {})
            detailed_state = str(status_data.get("detailedState") or "")
            game_season = int(game.get("season") or season or 0)

            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_team = home.get("team", {})
            away_team = away.get("team", {})

            home_team_id = home_team.get("id")
            away_team_id = away_team.get("id")
            if home_team_id is None or away_team_id is None:
                continue

            team_rows[int(home_team_id)] = (
                int(home_team_id),
                str(home_team.get("name") or f"Team {home_team_id}"),
                str(home_team.get("abbreviation") or home_team.get("teamCode") or f"T{home_team_id}"),
            )
            team_rows[int(away_team_id)] = (
                int(away_team_id),
                str(away_team.get("name") or f"Team {away_team_id}"),
                str(away_team.get("abbreviation") or away_team.get("teamCode") or f"T{away_team_id}"),
            )

            home_probable = home.get("probablePitcher", {}) or {}
            away_probable = away.get("probablePitcher", {}) or {}

            home_pitcher_id = home_probable.get("id")
            away_pitcher_id = away_probable.get("id")

            if home_pitcher_id is not None:
                pitcher_rows[int(home_pitcher_id)] = (
                    int(home_pitcher_id),
                    str(home_probable.get("fullName") or f"Pitcher {home_pitcher_id}"),
                    int(home_team_id),
                    "",
                )
            if away_pitcher_id is not None:
                pitcher_rows[int(away_pitcher_id)] = (
                    int(away_pitcher_id),
                    str(away_probable.get("fullName") or f"Pitcher {away_pitcher_id}"),
                    int(away_team_id),
                    "",
                )

            home_score = home.get("score")
            away_score = away.get("score")
            if home_score is not None:
                home_score = int(home_score)
            if away_score is not None:
                away_score = int(away_score)

            game_rows.append(
                (
                    int(game_pk),
                    game_date,
                    game_season,
                    detailed_state,
                    int(home_team_id),
                    int(away_team_id),
                    home_score,
                    away_score,
                    int(home_pitcher_id) if home_pitcher_id is not None else None,
                    int(away_pitcher_id) if away_pitcher_id is not None else None,
                )
            )

    return (
        sorted(team_rows.values(), key=lambda row: row[0]),
        sorted(pitcher_rows.values(), key=lambda row: row[0]),
        game_rows,
    )


def upsert_teams(rows: list[tuple[int, str, str]]) -> int:
    """Upsert real team rows so future matchers can use correct names."""
    if not rows:
        return 0

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO teams (team_id, team_name, team_abbr)
            VALUES (?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                team_name = excluded.team_name,
                team_abbr = excluded.team_abbr
            """,
            rows,
        )
        connection.commit()
    return len(rows)


def upsert_pitchers(rows: list[tuple[int, str, int | None, str]]) -> int:
    """Upsert probable starters when the schedule API provides them."""
    if not rows:
        return 0

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO starting_pitchers (pitcher_id, pitcher_name, team_id, throws_hand)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(pitcher_id) DO UPDATE SET
                pitcher_name = excluded.pitcher_name,
                team_id = excluded.team_id
            """,
            rows,
        )
        connection.commit()
    return len(rows)


def upsert_games(rows: list[tuple[Any, ...]]) -> int:
    """Upsert schedule rows so completed and upcoming games share one table."""
    if not rows:
        return 0

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO games (
                game_id,
                game_date,
                season,
                status,
                home_team_id,
                away_team_id,
                home_score,
                away_score,
                home_starting_pitcher_id,
                away_starting_pitcher_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                game_date = excluded.game_date,
                season = excluded.season,
                status = excluded.status,
                home_team_id = excluded.home_team_id,
                away_team_id = excluded.away_team_id,
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                home_starting_pitcher_id = COALESCE(excluded.home_starting_pitcher_id, games.home_starting_pitcher_id),
                away_starting_pitcher_id = COALESCE(excluded.away_starting_pitcher_id, games.away_starting_pitcher_id)
            """,
            rows,
        )
        connection.commit()
    return len(rows)


def count_games() -> int:
    """Return the current row count in games."""
    with get_connection() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM games").fetchone()[0])


def load_historical_games(
    season: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, int]:
    """Load schedule rows into SQLite."""
    initialize_database()
    dates = fetch_schedule(season=season, start_date=start_date, end_date=end_date)
    team_rows, pitcher_rows, game_rows = parse_schedule_rows(dates, season=season)
    teams_upserted = upsert_teams(team_rows)
    pitchers_upserted = upsert_pitchers(pitcher_rows)
    games_upserted = upsert_games(game_rows)
    results = {
        "date_groups": len(dates),
        "teams_upserted": teams_upserted,
        "pitchers_upserted": pitchers_upserted,
        "games_upserted": games_upserted,
        "total_games": count_games(),
    }
    LOGGER.info("Historical game ingestion results: %s", results)
    return results


def main() -> None:
    """Run the schedule ingestion script."""
    args = build_parser().parse_args()
    configure_logging(args.log_level)

    if args.season is None and not args.start_date and not args.end_date:
        current_year = datetime.now().year
        args.start_date = date.today().isoformat()
        args.end_date = (date.today() + timedelta(days=3)).isoformat()
        LOGGER.info(
            "No date range or season provided. Defaulting to upcoming window %s through %s.",
            args.start_date,
            args.end_date,
        )
        args.season = current_year

    results = load_historical_games(
        season=args.season,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(
        "Loaded {games_upserted} games | teams {teams_upserted} | pitchers {pitchers_upserted} | total games {total_games}".format(
            **results
        )
    )


if __name__ == "__main__":
    main()
