"""Load beginner-friendly MLB team and pitcher stats from the MLB Stats API."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from collections import defaultdict
from typing import Any

import requests

from app.db.connection import get_connection
from app.db.schema import initialize_database

LOGGER = logging.getLogger(__name__)
GAME_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
FIP_CONSTANT = 3.2


def build_parser() -> argparse.ArgumentParser:
    """Create a small CLI parser for MLB stat ingestion."""
    parser = argparse.ArgumentParser(
        description="Load MLB team and pitcher daily stats into SQLite.",
    )
    parser.add_argument("--start-date", help="Optional start date filter in YYYY-MM-DD format.")
    parser.add_argument("--end-date", help="Optional end date filter in YYYY-MM-DD format.")
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional game limit for quick testing.",
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


def parse_innings_pitched(value: Any) -> float:
    """Convert MLB innings strings like 5.1 into decimal innings."""
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        value = str(value)
    text = str(value).strip()
    if "." not in text:
        try:
            return float(text)
        except ValueError:
            return 0.0

    whole_text, outs_text = text.split(".", 1)
    try:
        whole_innings = int(whole_text)
        outs = int(outs_text[:1])
    except ValueError:
        return 0.0
    outs = max(0, min(outs, 2))
    return whole_innings + (outs / 3.0)


def calculate_fip(home_runs: int, walks: int, hit_batters: int, strikeouts: int, innings_pitched: float) -> float | None:
    """Calculate a simple FIP estimate from box-score components."""
    if innings_pitched <= 0:
        return None
    raw_fip = ((13 * home_runs) + (3 * (walks + hit_batters)) - (2 * strikeouts)) / innings_pitched
    return round(raw_fip + FIP_CONSTANT, 3)


def load_target_games(
    connection: sqlite3.Connection,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Load completed games that should receive stat details."""
    query = """
        SELECT
            game_id,
            game_date,
            season,
            home_score,
            away_score
        FROM games
        WHERE home_score IS NOT NULL
          AND away_score IS NOT NULL
    """
    params: list[Any] = []
    if start_date:
        query += " AND game_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND game_date <= ?"
        params.append(end_date)
    query += " ORDER BY game_date, game_id"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = connection.execute(query, params).fetchall()
    games = [
        {
            "game_id": int(row[0]),
            "game_date": str(row[1]),
            "season": int(row[2]),
            "home_score": int(row[3]),
            "away_score": int(row[4]),
        }
        for row in rows
    ]
    LOGGER.info("Loaded %s target games for stat ingestion", len(games))
    return games


def fetch_game_feed(session: requests.Session, game_id: int) -> dict[str, Any]:
    """Fetch one game feed payload from the MLB Stats API."""
    response = session.get(GAME_FEED_URL.format(game_pk=game_id), timeout=30)
    response.raise_for_status()
    return response.json()


def extract_team_row(team_data: dict[str, Any]) -> tuple[int, str, str]:
    """Normalize one team row for the teams table."""
    return (
        int(team_data["id"]),
        str(team_data["name"]),
        str(team_data["abbreviation"]),
    )


def extract_starter_info(feed_data: dict[str, Any], side: str) -> dict[str, Any] | None:
    """Return the actual starter info for one team side of a game."""
    team_box = feed_data.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {})
    game_players = feed_data.get("gameData", {}).get("players", {})
    probable_pitchers = feed_data.get("gameData", {}).get("probablePitchers", {})

    starter_id: int | None = None
    for pitcher_id in team_box.get("pitchers", []):
        player_box = team_box.get("players", {}).get(f"ID{pitcher_id}", {})
        pitching_stats = player_box.get("stats", {}).get("pitching", {})
        if int(pitching_stats.get("gamesStarted", 0) or 0) >= 1:
            starter_id = int(pitcher_id)
            break

    if starter_id is None:
        probable_pitcher = probable_pitchers.get(side) or {}
        if probable_pitcher.get("id") is not None:
            starter_id = int(probable_pitcher["id"])

    if starter_id is None:
        return None

    player_key = f"ID{starter_id}"
    player_game_data = game_players.get(player_key, {})
    player_box = team_box.get("players", {}).get(player_key, {})
    pitching_stats = player_box.get("stats", {}).get("pitching", {})

    innings_pitched = parse_innings_pitched(pitching_stats.get("inningsPitched"))
    earned_runs = int(pitching_stats.get("earnedRuns", 0) or 0)
    strikeouts = int(pitching_stats.get("strikeOuts", 0) or 0)
    walks = int(pitching_stats.get("baseOnBalls", 0) or 0)
    hit_batters = int(pitching_stats.get("hitBatsmen", 0) or 0)
    home_runs = int(pitching_stats.get("homeRuns", 0) or 0)

    return {
        "pitcher_id": starter_id,
        "pitcher_name": str(
            player_game_data.get("fullName")
            or player_box.get("person", {}).get("fullName")
            or probable_pitchers.get(side, {}).get("fullName")
            or f"Pitcher {starter_id}"
        ),
        "team_id": int(team_box.get("team", {}).get("id")),
        "throws_hand": str(player_game_data.get("pitchHand", {}).get("code", "") or ""),
        "innings_pitched": innings_pitched,
        "earned_runs": earned_runs,
        "strikeouts": strikeouts,
        "walks": walks,
        "hit_batters": hit_batters,
        "home_runs": home_runs,
    }


def build_team_day_update(
    existing_entry: dict[str, Any] | None,
    team_id: int,
    game_date: str,
    wins: int,
    losses: int,
    runs_scored: float,
    runs_allowed: float,
) -> dict[str, Any]:
    """Aggregate one team-day row for rerunnable daily stats."""
    if existing_entry is None:
        return {
            "team_id": team_id,
            "game_date": game_date,
            "wins": wins,
            "losses": losses,
            "runs_scored": float(runs_scored),
            "runs_allowed": float(runs_allowed),
        }

    existing_entry["wins"] = max(int(existing_entry["wins"]), int(wins))
    existing_entry["losses"] = max(int(existing_entry["losses"]), int(losses))
    existing_entry["runs_scored"] = float(existing_entry["runs_scored"]) + float(runs_scored)
    existing_entry["runs_allowed"] = float(existing_entry["runs_allowed"]) + float(runs_allowed)
    return existing_entry


def build_pitcher_day_update(
    existing_entry: dict[str, Any] | None,
    starter_info: dict[str, Any],
    game_date: str,
) -> dict[str, Any]:
    """Aggregate one starter-day row for rerunnable daily stats."""
    if existing_entry is None:
        return {
            "pitcher_id": starter_info["pitcher_id"],
            "game_date": game_date,
            "innings_pitched": float(starter_info["innings_pitched"]),
            "earned_runs": int(starter_info["earned_runs"]),
            "strikeouts": int(starter_info["strikeouts"]),
            "walks": int(starter_info["walks"]),
            "_home_runs": int(starter_info["home_runs"]),
            "_hit_batters": int(starter_info["hit_batters"]),
        }

    existing_entry["innings_pitched"] = float(existing_entry["innings_pitched"]) + float(starter_info["innings_pitched"])
    existing_entry["earned_runs"] = int(existing_entry["earned_runs"]) + int(starter_info["earned_runs"])
    existing_entry["strikeouts"] = int(existing_entry["strikeouts"]) + int(starter_info["strikeouts"])
    existing_entry["walks"] = int(existing_entry["walks"]) + int(starter_info["walks"])
    existing_entry["_home_runs"] = int(existing_entry["_home_runs"]) + int(starter_info["home_runs"])
    existing_entry["_hit_batters"] = int(existing_entry["_hit_batters"]) + int(starter_info["hit_batters"])
    return existing_entry


def prepare_stat_payloads(
    games: list[dict[str, Any]],
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, int | None, str]], list[tuple[int, int | None, int | None, int]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch feeds and turn them into SQLite-ready rows."""
    session = requests.Session()
    teams: dict[int, tuple[int, str, str]] = {}
    pitchers: dict[int, tuple[int, str, int | None, str]] = {}
    game_updates: list[tuple[int, int | None, int | None, int]] = []
    team_day_rows: dict[tuple[int, str], dict[str, Any]] = {}
    pitcher_day_rows: dict[tuple[int, str], dict[str, Any]] = {}

    for index, game in enumerate(games, start=1):
        feed_data = fetch_game_feed(session, game["game_id"])
        game_date = str(feed_data.get("gameData", {}).get("datetime", {}).get("originalDate") or game["game_date"])
        game_teams = feed_data.get("gameData", {}).get("teams", {})
        live_teams = feed_data.get("liveData", {}).get("boxscore", {}).get("teams", {})

        for side in ["home", "away"]:
            team_data = game_teams.get(side, {})
            if team_data.get("id") is not None:
                teams[int(team_data["id"])] = extract_team_row(team_data)

        home_team = game_teams.get("home", {})
        away_team = game_teams.get("away", {})
        home_team_id = int(home_team["id"])
        away_team_id = int(away_team["id"])
        home_record = home_team.get("record", {})
        away_record = away_team.get("record", {})

        team_day_rows[(home_team_id, game_date)] = build_team_day_update(
            team_day_rows.get((home_team_id, game_date)),
            team_id=home_team_id,
            game_date=game_date,
            wins=int(home_record.get("wins", 0) or 0),
            losses=int(home_record.get("losses", 0) or 0),
            runs_scored=float(game["home_score"]),
            runs_allowed=float(game["away_score"]),
        )
        team_day_rows[(away_team_id, game_date)] = build_team_day_update(
            team_day_rows.get((away_team_id, game_date)),
            team_id=away_team_id,
            game_date=game_date,
            wins=int(away_record.get("wins", 0) or 0),
            losses=int(away_record.get("losses", 0) or 0),
            runs_scored=float(game["away_score"]),
            runs_allowed=float(game["home_score"]),
        )

        home_starter = extract_starter_info(feed_data, "home")
        away_starter = extract_starter_info(feed_data, "away")

        if home_starter is not None:
            pitchers[home_starter["pitcher_id"]] = (
                int(home_starter["pitcher_id"]),
                str(home_starter["pitcher_name"]),
                int(home_starter["team_id"]) if home_starter.get("team_id") is not None else None,
                str(home_starter.get("throws_hand", "")),
            )
            pitcher_day_rows[(home_starter["pitcher_id"], game_date)] = build_pitcher_day_update(
                pitcher_day_rows.get((home_starter["pitcher_id"], game_date)),
                home_starter,
                game_date,
            )

        if away_starter is not None:
            pitchers[away_starter["pitcher_id"]] = (
                int(away_starter["pitcher_id"]),
                str(away_starter["pitcher_name"]),
                int(away_starter["team_id"]) if away_starter.get("team_id") is not None else None,
                str(away_starter.get("throws_hand", "")),
            )
            pitcher_day_rows[(away_starter["pitcher_id"], game_date)] = build_pitcher_day_update(
                pitcher_day_rows.get((away_starter["pitcher_id"], game_date)),
                away_starter,
                game_date,
            )

        game_updates.append(
            (
                int(home_starter["pitcher_id"]) if home_starter is not None else None,
                int(away_starter["pitcher_id"]) if away_starter is not None else None,
                int(game["game_id"]),
            )
        )

        LOGGER.info("Prepared stat payload %s/%s for game %s", index, len(games), game["game_id"])

    finalized_pitcher_rows: list[dict[str, Any]] = []
    for row in pitcher_day_rows.values():
        finalized_pitcher_rows.append(
            {
                "pitcher_id": int(row["pitcher_id"]),
                "game_date": str(row["game_date"]),
                "innings_pitched": round(float(row["innings_pitched"]), 3),
                "earned_runs": int(row["earned_runs"]),
                "strikeouts": int(row["strikeouts"]),
                "walks": int(row["walks"]),
                "fip": calculate_fip(
                    home_runs=int(row["_home_runs"]),
                    walks=int(row["walks"]),
                    hit_batters=int(row["_hit_batters"]),
                    strikeouts=int(row["strikeouts"]),
                    innings_pitched=float(row["innings_pitched"]),
                ),
            }
        )

    return (
        sorted(teams.values(), key=lambda row: row[0]),
        sorted(pitchers.values(), key=lambda row: row[0]),
        game_updates,
        list(team_day_rows.values()),
        finalized_pitcher_rows,
    )


def upsert_teams(connection: sqlite3.Connection, team_rows: list[tuple[int, str, str]]) -> int:
    """Upsert real team names and abbreviations."""
    if not team_rows:
        return 0
    connection.executemany(
        """
        INSERT INTO teams (team_id, team_name, team_abbr)
        VALUES (?, ?, ?)
        ON CONFLICT(team_id) DO UPDATE SET
            team_name = excluded.team_name,
            team_abbr = excluded.team_abbr
        """,
        team_rows,
    )
    return len(team_rows)


def upsert_pitchers(connection: sqlite3.Connection, pitcher_rows: list[tuple[int, str, int | None, str]]) -> int:
    """Upsert starter rows."""
    if not pitcher_rows:
        return 0
    connection.executemany(
        """
        INSERT INTO starting_pitchers (pitcher_id, pitcher_name, team_id, throws_hand)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(pitcher_id) DO UPDATE SET
            pitcher_name = excluded.pitcher_name,
            team_id = excluded.team_id,
            throws_hand = excluded.throws_hand
        """,
        pitcher_rows,
    )
    return len(pitcher_rows)


def update_game_starters(connection: sqlite3.Connection, game_updates: list[tuple[int | None, int | None, int]]) -> int:
    """Save actual starter ids back onto games."""
    if not game_updates:
        return 0
    connection.executemany(
        """
        UPDATE games
        SET home_starting_pitcher_id = ?, away_starting_pitcher_id = ?
        WHERE game_id = ?
        """,
        game_updates,
    )
    return len(game_updates)


def upsert_team_daily_stats(connection: sqlite3.Connection, team_day_rows: list[dict[str, Any]]) -> int:
    """Upsert team daily stats rows."""
    if not team_day_rows:
        return 0
    connection.executemany(
        """
        INSERT INTO team_daily_stats (
            team_id,
            game_date,
            wins,
            losses,
            runs_scored,
            runs_allowed
        )
        VALUES (
            :team_id,
            :game_date,
            :wins,
            :losses,
            :runs_scored,
            :runs_allowed
        )
        ON CONFLICT(team_id, game_date) DO UPDATE SET
            wins = excluded.wins,
            losses = excluded.losses,
            runs_scored = excluded.runs_scored,
            runs_allowed = excluded.runs_allowed
        """,
        team_day_rows,
    )
    return len(team_day_rows)


def upsert_pitcher_daily_stats(connection: sqlite3.Connection, pitcher_day_rows: list[dict[str, Any]]) -> int:
    """Upsert pitcher daily stats rows."""
    if not pitcher_day_rows:
        return 0
    connection.executemany(
        """
        INSERT INTO pitcher_daily_stats (
            pitcher_id,
            game_date,
            innings_pitched,
            earned_runs,
            strikeouts,
            walks,
            fip
        )
        VALUES (
            :pitcher_id,
            :game_date,
            :innings_pitched,
            :earned_runs,
            :strikeouts,
            :walks,
            :fip
        )
        ON CONFLICT(pitcher_id, game_date) DO UPDATE SET
            innings_pitched = excluded.innings_pitched,
            earned_runs = excluded.earned_runs,
            strikeouts = excluded.strikeouts,
            walks = excluded.walks,
            fip = excluded.fip
        """,
        pitcher_day_rows,
    )
    return len(pitcher_day_rows)


def load_mlb_stats(start_date: str | None = None, end_date: str | None = None, limit: int | None = None) -> dict[str, int]:
    """Load MLB team and starter daily stats into SQLite."""
    initialize_database()
    with get_connection() as connection:
        target_games = load_target_games(
            connection,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if not target_games:
            LOGGER.warning("No completed games matched the requested date range.")
            return {
                "games_processed": 0,
                "teams_upserted": 0,
                "pitchers_upserted": 0,
                "games_updated": 0,
                "team_daily_stats_upserted": 0,
                "pitcher_daily_stats_upserted": 0,
            }

        team_rows, pitcher_rows, game_updates, team_day_rows, pitcher_day_rows = prepare_stat_payloads(target_games)
        teams_upserted = upsert_teams(connection, team_rows)
        pitchers_upserted = upsert_pitchers(connection, pitcher_rows)
        games_updated = update_game_starters(connection, game_updates)
        team_stats_upserted = upsert_team_daily_stats(connection, team_day_rows)
        pitcher_stats_upserted = upsert_pitcher_daily_stats(connection, pitcher_day_rows)
        connection.commit()

    results = {
        "games_processed": len(target_games),
        "teams_upserted": teams_upserted,
        "pitchers_upserted": pitchers_upserted,
        "games_updated": games_updated,
        "team_daily_stats_upserted": team_stats_upserted,
        "pitcher_daily_stats_upserted": pitcher_stats_upserted,
    }
    LOGGER.info("MLB stat ingestion results: %s", results)
    return results


def main() -> None:
    """Run the MLB stat ingestion script."""
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    results = load_mlb_stats(
        start_date=args.start_date,
        end_date=args.end_date,
        limit=args.limit,
    )
    print(
        "Processed {games_processed} games | teams {teams_upserted} | pitchers {pitchers_upserted} | "
        "team stats {team_daily_stats_upserted} | pitcher stats {pitcher_daily_stats_upserted}".format(**results)
    )


if __name__ == "__main__":
    main()
