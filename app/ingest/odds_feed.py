"""Load MLB moneyline odds into the odds_snapshots table."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from typing import Any

import requests

from app.config import DB_PATH
from app.db.connection import get_connection
from app.db.schema import initialize_database

LOGGER = logging.getLogger(__name__)
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
REQUEST_TIMEOUT = 30
DEFAULT_REGIONS = "us"
DEFAULT_MARKETS = "h2h"
DEFAULT_ODDS_FORMAT = "american"


def build_parser() -> argparse.ArgumentParser:
    """Create a command-line parser for the odds feed."""
    parser = argparse.ArgumentParser(
        description="Load MLB moneyline odds into the odds_snapshots table."
    )
    parser.add_argument(
        "--start-date",
        help="Optional start date in YYYY-MM-DD format for matching games already in the database.",
    )
    parser.add_argument(
        "--end-date",
        help="Optional end date in YYYY-MM-DD format for matching games already in the database.",
    )
    parser.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        help="Odds API regions value. The default is 'us'.",
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


def get_api_key() -> str:
    """Read the Odds API key from the environment."""
    api_key = os.getenv("ODDS_API_KEY")
    if not api_key:
        raise ValueError("ODDS_API_KEY is missing. Add it to your environment before running the odds feed.")
    return api_key


def fetch_odds_payload(api_key: str, regions: str) -> list[dict[str, Any]]:
    """Fetch current MLB moneyline odds from The Odds API."""
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": DEFAULT_MARKETS,
        "oddsFormat": DEFAULT_ODDS_FORMAT,
    }
    response = requests.get(ODDS_API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    return payload


def load_game_lookup(start_date: str | None, end_date: str | None) -> dict[tuple[str, str, str], int]:
    """Load existing games so odds rows can be matched to a game_id."""
    query = """
        SELECT
            games.game_id,
            games.game_date,
            home_teams.team_name AS home_team_name,
            away_teams.team_name AS away_team_name
        FROM games
        JOIN teams AS home_teams ON games.home_team_id = home_teams.team_id
        JOIN teams AS away_teams ON games.away_team_id = away_teams.team_id
        WHERE 1 = 1
    """
    parameters: list[str] = []

    if start_date:
        query += " AND games.game_date >= ?"
        parameters.append(start_date)

    if end_date:
        query += " AND games.game_date <= ?"
        parameters.append(end_date)

    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()

    lookup: dict[tuple[str, str, str], int] = {}
    for game_id, game_date, home_team_name, away_team_name in rows:
        lookup[(str(game_date), str(home_team_name), str(away_team_name))] = int(game_id)

    LOGGER.info("Loaded %s games for odds matching from %s", len(lookup), DB_PATH)
    return lookup


def parse_snapshot_time(value: str | None, fallback_time: str) -> str:
    """Return a snapshot timestamp using the bookmaker time when available."""
    return value or fallback_time


def extract_moneylines(outcomes: list[dict[str, Any]], home_team: str, away_team: str) -> tuple[int | None, int | None]:
    """Read the home and away moneylines from one bookmaker market."""
    home_moneyline = None
    away_moneyline = None

    for outcome in outcomes:
        name = outcome.get("name")
        price = outcome.get("price")

        if name == home_team:
            home_moneyline = int(price) if price is not None else None
        elif name == away_team:
            away_moneyline = int(price) if price is not None else None

    return home_moneyline, away_moneyline


def build_odds_rows(
    payload: list[dict[str, Any]],
    game_lookup: dict[tuple[str, str, str], int],
) -> tuple[list[dict[str, Any]], int, int]:
    """Normalize odds payload rows into the odds_snapshots table shape."""
    normalized_rows: list[dict[str, Any]] = []
    fetched_count = 0
    skipped_count = 0

    for event in payload:
        game_date = str(event.get("commence_time", ""))[:10]
        home_team = event.get("home_team")
        away_team = event.get("away_team")
        game_id = game_lookup.get((game_date, str(home_team), str(away_team)))

        if game_id is None:
            for bookmaker in event.get("bookmakers", []):
                fetched_count += 1
                skipped_count += 1
            continue

        for bookmaker in event.get("bookmakers", []):
            fetched_count += 1
            sportsbook_name = bookmaker.get("title")
            snapshot_time = parse_snapshot_time(bookmaker.get("last_update"), datetime.utcnow().isoformat())
            markets = bookmaker.get("markets", [])

            moneyline_market = next((market for market in markets if market.get("key") == "h2h"), None)
            if moneyline_market is None:
                skipped_count += 1
                continue

            outcomes = moneyline_market.get("outcomes", [])
            home_moneyline, away_moneyline = extract_moneylines(outcomes, str(home_team), str(away_team))
            if sportsbook_name is None or home_moneyline is None or away_moneyline is None:
                skipped_count += 1
                continue

            normalized_rows.append(
                {
                    "game_id": game_id,
                    "sportsbook_name": str(sportsbook_name),
                    "snapshot_time": snapshot_time,
                    "home_moneyline": home_moneyline,
                    "away_moneyline": away_moneyline,
                }
            )

    return normalized_rows, fetched_count, skipped_count


def load_existing_keys(rows: list[dict[str, Any]]) -> set[tuple[int, str, str]]:
    """Load existing snapshot keys so duplicates can be skipped before insert."""
    if not rows:
        return set()

    game_ids = sorted({row["game_id"] for row in rows})
    placeholders = ", ".join("?" for _ in game_ids)
    query = (
        "SELECT game_id, sportsbook_name, snapshot_time "
        f"FROM odds_snapshots WHERE game_id IN ({placeholders})"
    )

    with get_connection() as connection:
        existing_rows = connection.execute(query, game_ids).fetchall()

    return {(int(game_id), str(sportsbook_name), str(snapshot_time)) for game_id, sportsbook_name, snapshot_time in existing_rows}


def insert_odds_rows(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert normalized odds rows and skip duplicates."""
    if not rows:
        return 0, 0

    existing_keys = load_existing_keys(rows)
    rows_to_insert = []
    duplicate_count = 0

    for row in rows:
        key = (int(row["game_id"]), str(row["sportsbook_name"]), str(row["snapshot_time"]))
        if key in existing_keys:
            duplicate_count += 1
            continue

        existing_keys.add(key)
        rows_to_insert.append(row)

    if not rows_to_insert:
        return 0, duplicate_count

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO odds_snapshots (
                game_id,
                sportsbook_name,
                snapshot_time,
                home_moneyline,
                away_moneyline
            )
            VALUES (
                :game_id,
                :sportsbook_name,
                :snapshot_time,
                :home_moneyline,
                :away_moneyline
            )
            """,
            rows_to_insert,
        )
        connection.commit()

    return len(rows_to_insert), duplicate_count


def load_odds_feed(start_date: str | None = None, end_date: str | None = None, regions: str = DEFAULT_REGIONS) -> int:
    """Fetch MLB moneyline odds and save them into odds_snapshots."""
    initialize_database()
    api_key = get_api_key()
    payload = fetch_odds_payload(api_key, regions)
    game_lookup = load_game_lookup(start_date, end_date)
    normalized_rows, fetched_count, skipped_count = build_odds_rows(payload, game_lookup)
    inserted_count, duplicate_count = insert_odds_rows(normalized_rows)
    total_skipped = skipped_count + duplicate_count

    LOGGER.info("Fetched %s odds records", fetched_count)
    LOGGER.info("Inserted %s odds rows", inserted_count)
    LOGGER.info("Skipped %s odds rows", total_skipped)
    return inserted_count


def main() -> None:
    """Run the odds ingestion script."""
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    inserted_count = load_odds_feed(
        start_date=args.start_date,
        end_date=args.end_date,
        regions=args.regions,
    )
    print(f"Inserted {inserted_count} odds rows into {DB_PATH}")


if __name__ == "__main__":
    main()
