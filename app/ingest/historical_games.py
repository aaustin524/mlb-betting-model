from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import requests

from app.db.connection import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def fetch_schedule(season: int = 2024) -> list[dict]:
    params = {
        "sportId": 1,
        "season": season,
        "gameType": "R",
    }
    response = requests.get(SCHEDULE_URL, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("dates", [])


def parse_games(dates: list[dict], season: int) -> list[tuple]:
    rows: list[tuple] = []

    for day in dates:
        game_date = day.get("date")
        for game in day.get("games", []):
            status = game.get("status", {}).get("detailedState")

            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})

            home_team = home.get("team", {})
            away_team = away.get("team", {})

            home_score = home.get("score")
            away_score = away.get("score")

            # only keep completed regular-season games with scores
            if status != "Final":
                continue
            if home_score is None or away_score is None:
                continue
            if home_team.get("id") is None or away_team.get("id") is None:
                continue

            rows.append(
                (
                    game.get("gamePk"),
                    game_date,
                    season,
                    status,
                    home_team.get("id"),
                    away_team.get("id"),
                    home_score,
                    away_score,
                    None,
                    None,
                )
            )

    return rows


def insert_teams(rows: list[tuple]) -> None:
    teams: dict[int, tuple[int, str, str]] = {}

    for row in rows:
        home_team_id = row[4]
        away_team_id = row[5]

        # placeholder names/abbrs so foreign keys can succeed
        if home_team_id not in teams:
            teams[home_team_id] = (home_team_id, f"Team {home_team_id}", f"T{home_team_id}")
        if away_team_id not in teams:
            teams[away_team_id] = (away_team_id, f"Team {away_team_id}", f"T{away_team_id}")

    if not teams:
        return

    sql = """
    INSERT OR IGNORE INTO teams (team_id, team_name, team_abbr)
    VALUES (?, ?, ?)
    """

    with get_connection() as conn:
        conn.executemany(sql, list(teams.values()))
        conn.commit()


def insert_games(rows: list[tuple]) -> None:
    sql = """
    INSERT OR IGNORE INTO games (
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
    """

    with get_connection() as conn:
        conn.executemany(sql, rows)
        conn.commit()


def count_games() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM games")
        return cursor.fetchone()[0]


def main() -> None:
    season = 2024

    logging.info("Fetching MLB schedule for season %s", season)
    dates = fetch_schedule(season=season)
    logging.info("Fetched %s date groups", len(dates))

    rows = parse_games(dates, season=season)
    logging.info("Parsed %s final games", len(rows))

    if rows:
        logging.info("First parsed row: %s", rows[0])

    insert_teams(rows)
    insert_games(rows)

    total_games = count_games()
    logging.info("Total rows now in games table: %s", total_games)


if __name__ == "__main__":
    main()