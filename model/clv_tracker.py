"""Closing-line tracking helpers for dashboard snapshot bets."""

from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

import pandas as pd
import requests

try:
    from db.connection import get_connection
    from db.schema import initialize_database
except ModuleNotFoundError:
    from app.db.connection import get_connection
    from app.db.schema import initialize_database
from app.runtime_env import get_odds_api_key


ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds"
DEFAULT_REGIONS = "us"
DEFAULT_MARKETS = "h2h,totals"
DEFAULT_ODDS_FORMAT = "american"
REQUEST_TIMEOUT = 20
PREFERRED_SPORTSBOOKS = [
    "draftkings",
    "fanduel",
    "betmgm",
    "caesars",
]


def normalize_team_name(team_name: str | None) -> str:
    """Normalize team names so dashboard rows can match API event names."""
    if team_name is None or pd.isna(team_name):
        return ""

    normalized = str(team_name).strip().lower()
    replacements = {
        ".": "",
        ",": "",
        "'": "",
        "-": " ",
    }
    for old_value, new_value in replacements.items():
        normalized = normalized.replace(old_value, new_value)

    tokens = [token for token in normalized.split() if token not in {"the"}]
    normalized_value = " ".join(tokens)
    alias_map = {
        "athletics": "oakland athletics",
    }
    return alias_map.get(normalized_value, normalized_value)


def normalize_sportsbook_name(sportsbook_name: str | None) -> str:
    """Normalize sportsbook names so tracked bets can match historical odds rows."""
    if sportsbook_name is None or pd.isna(sportsbook_name):
        return ""
    return str(sportsbook_name).strip().lower()


def american_odds_to_implied_prob(odds_value: Any) -> float | None:
    """Convert an American price into an implied probability."""
    if odds_value is None or pd.isna(odds_value):
        return None

    try:
        odds = float(odds_value)
    except (TypeError, ValueError):
        return None

    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def american_odds_profit(odds_value: Any) -> float | None:
    """Return profit on a 1-unit stake for a winning American odds bet."""
    if odds_value is None or pd.isna(odds_value):
        return None

    try:
        odds = float(odds_value)
    except (TypeError, ValueError):
        return None

    if odds == 0:
        return None
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


def choose_preferred_bookmaker(bookmakers: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Choose one sportsbook for open/close comparisons using a stable preference order."""
    if not bookmakers:
        return None

    bookmaker_lookup = {
        bookmaker.get("key"): bookmaker
        for bookmaker in bookmakers
        if bookmaker.get("key")
    }
    for bookmaker_key in PREFERRED_SPORTSBOOKS:
        if bookmaker_key in bookmaker_lookup:
            return bookmaker_lookup[bookmaker_key]
    return bookmakers[0]


def parse_bookmaker_h2h_market(bookmaker: dict[str, Any] | None, away_team: str, home_team: str) -> dict[str, int | None]:
    """Read one sportsbook's moneyline market into a compact dict."""
    market_prices = {
        "away_moneyline": None,
        "home_moneyline": None,
    }
    if bookmaker is None:
        return market_prices

    for market in bookmaker.get("markets", []):
        if market.get("key") != "h2h":
            continue
        for outcome in market.get("outcomes", []):
            if outcome.get("name") == away_team and outcome.get("price") is not None:
                market_prices["away_moneyline"] = int(float(outcome["price"]))
            elif outcome.get("name") == home_team and outcome.get("price") is not None:
                market_prices["home_moneyline"] = int(float(outcome["price"]))
        return market_prices

    return market_prices


def parse_bookmaker_totals_market(bookmaker: dict[str, Any] | None) -> dict[str, float | int | None]:
    """Read one sportsbook's total and prices into a compact dict."""
    totals_prices = {
        "total_line": None,
        "over_price": None,
        "under_price": None,
    }
    if bookmaker is None:
        return totals_prices

    for market in bookmaker.get("markets", []):
        if market.get("key") != "totals":
            continue

        over_outcome = next(
            (outcome for outcome in market.get("outcomes", []) if outcome.get("name") == "Over"),
            None,
        )
        under_outcome = next(
            (outcome for outcome in market.get("outcomes", []) if outcome.get("name") == "Under"),
            None,
        )
        if over_outcome is None and under_outcome is None:
            continue

        point_value = None
        if over_outcome is not None:
            point_value = over_outcome.get("point")
            if over_outcome.get("price") is not None:
                totals_prices["over_price"] = int(float(over_outcome["price"]))
        if under_outcome is not None:
            if point_value is None:
                point_value = under_outcome.get("point")
            if under_outcome.get("price") is not None:
                totals_prices["under_price"] = int(float(under_outcome["price"]))
        if point_value is not None:
            totals_prices["total_line"] = float(point_value)

        return totals_prices

    return totals_prices


def fetch_current_market_map(regions: str = DEFAULT_REGIONS) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Fetch current h2h and totals markets for all MLB games."""
    api_key = get_odds_api_key()
    if not api_key:
        raise ValueError("ODDS_API_KEY is missing. Add it to your environment before updating closing lines.")

    response = requests.get(
        ODDS_API_BASE_URL,
        params={
            "apiKey": api_key,
            "regions": regions,
            "markets": DEFAULT_MARKETS,
            "oddsFormat": DEFAULT_ODDS_FORMAT,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    market_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in response.json():
        away_team = event.get("away_team")
        home_team = event.get("home_team")
        if not away_team or not home_team:
            continue

        event_date = str(event.get("commence_time", ""))[:10]
        selected_bookmaker = choose_preferred_bookmaker(event.get("bookmakers", []))
        h2h_market = parse_bookmaker_h2h_market(selected_bookmaker, str(away_team), str(home_team))
        totals_market = parse_bookmaker_totals_market(selected_bookmaker)

        market_map[(normalize_team_name(away_team), normalize_team_name(home_team), event_date)] = {
            **h2h_market,
            **totals_market,
            "sportsbook": selected_bookmaker.get("title") if selected_bookmaker else None,
            "market_timestamp_close": (
                selected_bookmaker.get("last_update")
                if selected_bookmaker is not None
                else datetime.utcnow().isoformat()
            ),
        }

    return market_map


def load_game_market_lookup() -> dict[int, tuple[str, str, str] | None]:
    """
    Load a game_id -> market matching key lookup from SQLite.

    This lets tracked-bet updates prefer the canonical `game_id` relationship
    instead of rebuilding identity from stored team text whenever possible.
    """
    query = """
        SELECT
            games.game_id,
            games.game_date,
            away_teams.team_name AS away_team_name,
            home_teams.team_name AS home_team_name
        FROM games
        JOIN teams AS away_teams ON games.away_team_id = away_teams.team_id
        JOIN teams AS home_teams ON games.home_team_id = home_teams.team_id
    """
    with get_connection() as connection:
        games_df = pd.read_sql_query(query, connection)

    game_lookup: dict[int, tuple[str, str, str] | None] = {}
    for _, row in games_df.iterrows():
        try:
            game_lookup[int(row["game_id"])] = (
                normalize_team_name(row["away_team_name"]),
                normalize_team_name(row["home_team_name"]),
                str(row["game_date"])[:10],
            )
        except (TypeError, ValueError):
            continue
    return game_lookup


def load_odds_history_lookup(game_ids: list[int] | None = None) -> dict[str, dict[Any, dict[str, Any]]]:
    """
    Load earliest and latest historical odds snapshots keyed by game and sportsbook.

    The lookup returns both sportsbook-specific rows and game-level fallbacks so
    tracked bets can prefer their chosen book without failing when older history
    only exists for a different sportsbook.
    """
    initialize_database()
    query = """
        SELECT
            game_id,
            sportsbook_name,
            snapshot_time,
            home_moneyline,
            away_moneyline,
            total_line,
            over_price,
            under_price
        FROM odds_snapshots
    """
    params: list[Any] = []
    if game_ids:
        placeholders = ", ".join("?" for _ in game_ids)
        query += f" WHERE game_id IN ({placeholders})"
        params.extend(game_ids)

    with get_connection() as connection:
        history_df = pd.read_sql_query(query, connection, params=params)

    if history_df.empty:
        return {"by_book": {}, "overall": {}}

    history_df["snapshot_time_dt"] = pd.to_datetime(history_df["snapshot_time"], errors="coerce")
    history_df = history_df.dropna(subset=["snapshot_time_dt"]).copy()
    if history_df.empty:
        return {"by_book": {}, "overall": {}}

    history_df["sportsbook_key"] = history_df["sportsbook_name"].map(normalize_sportsbook_name)
    history_df = history_df.sort_values(
        by=["game_id", "sportsbook_key", "snapshot_time_dt"],
        ascending=[True, True, True],
    )

    by_book: dict[tuple[int, str], dict[str, Any]] = {}
    for (game_id, sportsbook_key), group_df in history_df.groupby(["game_id", "sportsbook_key"], dropna=False):
        open_row = group_df.iloc[0].to_dict()
        close_row = group_df.iloc[-1].to_dict()
        by_book[(int(game_id), str(sportsbook_key))] = {
            "open": open_row,
            "close": close_row,
        }

    overall: dict[int, dict[str, Any]] = {}
    for game_id, group_df in history_df.groupby("game_id", dropna=False):
        sorted_group_df = group_df.sort_values(by=["snapshot_time_dt"], ascending=[True])
        overall[int(game_id)] = {
            "open": sorted_group_df.iloc[0].to_dict(),
            "close": sorted_group_df.iloc[-1].to_dict(),
        }

    return {"by_book": by_book, "overall": overall}


def get_historical_market_row(
    history_lookup: dict[str, dict[Any, dict[str, Any]]],
    game_id: int | None,
    sportsbook_name: str | None,
    side: str,
) -> dict[str, Any] | None:
    """Return the earliest or latest historical market row for one tracked bet."""
    if game_id is None:
        return None

    try:
        normalized_game_id = int(game_id)
    except (TypeError, ValueError):
        return None

    sportsbook_key = normalize_sportsbook_name(sportsbook_name)
    by_book = history_lookup.get("by_book", {})
    overall = history_lookup.get("overall", {})

    if sportsbook_key:
        book_entry = by_book.get((normalized_game_id, sportsbook_key))
        if book_entry is not None:
            return book_entry.get(side)

    overall_entry = overall.get(normalized_game_id)
    if overall_entry is not None:
        return overall_entry.get(side)
    return None


def calculate_side_clv_metrics(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """
    Calculate side CLV from opening and closing implied probabilities.

    Positive CLV means the bet beat the close from the bettor's perspective.
    """
    best_bet = row.get("best_bet") or row.get("Best Bet")
    away_team = row.get("away_team") or row.get("Away")
    home_team = row.get("home_team") or row.get("Home")

    if best_bet in {None, "Pass"} or pd.isna(best_bet):
        return None, None

    if best_bet == away_team:
        open_price = row.get("open_away_ml", row.get("Away Moneyline"))
        close_price = row.get("close_away_ml", row.get("Closing Away Moneyline"))
    elif best_bet == home_team:
        open_price = row.get("open_home_ml", row.get("Home Moneyline"))
        close_price = row.get("close_home_ml", row.get("Closing Home Moneyline"))
    else:
        return None, None

    opening_prob = american_odds_to_implied_prob(open_price)
    closing_prob = american_odds_to_implied_prob(close_price)
    if opening_prob is None or closing_prob is None:
        return None, None

    raw_line_diff = None
    try:
        raw_line_diff = round(float(close_price) - float(open_price), 2)
    except (TypeError, ValueError):
        raw_line_diff = None

    return round((closing_prob - opening_prob) * 100.0, 3), raw_line_diff


def calculate_total_clv_metrics(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """
    Calculate totals CLV using line movement first and price as a tiebreaker.

    Positive values mean the bettor got the better total or price before close.
    """
    best_total_bet = row.get("best_total_bet") or row.get("Best Total Bet")
    if best_total_bet in {None, "Pass"} or pd.isna(best_total_bet):
        return None, None

    try:
        open_total = float(row.get("open_total", row.get("Total Line")))
        close_total = float(row.get("close_total", row.get("Closing Total Line")))
    except (TypeError, ValueError):
        return None, None

    if best_total_bet == "Over":
        line_delta = close_total - open_total
        if abs(line_delta) > 1e-9:
            return round(line_delta, 3), round(line_delta, 3)
        opening_prob = american_odds_to_implied_prob(row.get("open_over_price", row.get("Over Price")))
        closing_prob = american_odds_to_implied_prob(row.get("close_over_price"))
    elif best_total_bet == "Under":
        line_delta = open_total - close_total
        if abs(line_delta) > 1e-9:
            return round(line_delta, 3), round(line_delta, 3)
        opening_prob = american_odds_to_implied_prob(row.get("open_under_price", row.get("Under Price")))
        closing_prob = american_odds_to_implied_prob(row.get("close_under_price"))
    else:
        return None, None

    if opening_prob is None or closing_prob is None:
        return None, round(line_delta, 3)
    return round((closing_prob - opening_prob) * 100.0, 3), round(line_delta, 3)


def load_unresolved_tracked_bets() -> pd.DataFrame:
    """Load tracked bets that are still open or missing closing market data."""
    initialize_database()
    query = """
        SELECT *
        FROM tracked_bets
        WHERE (
            bet_flag IN ('Lean', 'Strong Bet')
            OR total_bet_flag IN ('Lean', 'Strong Bet')
        )
          AND (grading_status IS NULL OR grading_status != 'graded')
    """
    with get_connection() as connection:
        tracked_bets_df = pd.read_sql_query(query, connection)
    return tracked_bets_df


def load_auto_gradable_tracked_bets() -> pd.DataFrame:
    """Load unresolved tracked bets that already have final game scores in SQLite."""
    initialize_database()
    query = """
        SELECT
            tracked_bets.*,
            games.status AS game_status,
            games.home_score AS game_home_score,
            games.away_score AS game_away_score
        FROM tracked_bets
        JOIN games ON tracked_bets.game_id = games.game_id
        WHERE (
            tracked_bets.bet_flag IN ('Lean', 'Strong Bet')
            OR tracked_bets.total_bet_flag IN ('Lean', 'Strong Bet')
        )
          AND (tracked_bets.grading_status IS NULL OR tracked_bets.grading_status != 'graded')
          AND games.home_score IS NOT NULL
          AND games.away_score IS NOT NULL
    """
    with get_connection() as connection:
        tracked_bets_df = pd.read_sql_query(query, connection)
    return tracked_bets_df


def grade_side_pick_metrics(row: dict[str, Any]) -> tuple[str | None, str, float | None, str | None]:
    """Grade the side bet outcome for one tracked-bet row."""
    best_bet = row.get("best_bet") or row.get("Best Bet")
    bet_flag = row.get("bet_flag") or row.get("Bet Flag")
    away_team = row.get("away_team") or row.get("Away")
    home_team = row.get("home_team") or row.get("Home")
    final_away_runs = row.get("final_away_runs", row.get("Final Away Runs"))
    final_home_runs = row.get("final_home_runs", row.get("Final Home Runs"))

    if best_bet in {None, "Pass"} or pd.isna(best_bet) or bet_flag not in {"Lean", "Strong Bet"}:
        return None, "Ungraded", None, None
    if pd.isna(final_away_runs) or pd.isna(final_home_runs):
        return best_bet, "Ungraded", None, "missing final score"

    try:
        final_away_runs = float(final_away_runs)
        final_home_runs = float(final_home_runs)
    except (TypeError, ValueError):
        return best_bet, "Ungraded", None, "invalid score entry"

    if best_bet == away_team:
        price = row.get("open_away_ml", row.get("away_moneyline", row.get("Away Moneyline")))
        if final_away_runs > final_home_runs:
            units = american_odds_profit(price)
            if units is None:
                return best_bet, "Ungraded", None, "missing side price"
            return best_bet, "Win", units, None
        if final_away_runs < final_home_runs:
            return best_bet, "Loss", -1.0, None
        return best_bet, "Push", 0.0, None

    if best_bet == home_team:
        price = row.get("open_home_ml", row.get("home_moneyline", row.get("Home Moneyline")))
        if final_home_runs > final_away_runs:
            units = american_odds_profit(price)
            if units is None:
                return best_bet, "Ungraded", None, "missing side price"
            return best_bet, "Win", units, None
        if final_home_runs < final_away_runs:
            return best_bet, "Loss", -1.0, None
        return best_bet, "Push", 0.0, None

    return best_bet, "Ungraded", None, "invalid side pick"


def grade_total_pick_metrics(row: dict[str, Any]) -> tuple[str | None, float | None, str, float | None, str | None]:
    """Grade the totals bet outcome for one tracked-bet row."""
    best_total_bet = row.get("best_total_bet") or row.get("Best Total Bet")
    total_bet_flag = row.get("total_bet_flag") or row.get("Total Bet Flag")
    total_line = row.get("open_total", row.get("total_line", row.get("Total Line")))
    final_away_runs = row.get("final_away_runs", row.get("Final Away Runs"))
    final_home_runs = row.get("final_home_runs", row.get("Final Home Runs"))

    if (
        best_total_bet in {None, "Pass"}
        or pd.isna(best_total_bet)
        or total_bet_flag not in {"Lean", "Strong Bet"}
        or pd.isna(total_line)
    ):
        return None, None, "Ungraded", None, None
    if pd.isna(final_away_runs) or pd.isna(final_home_runs):
        return best_total_bet, None, "Ungraded", None, "missing final score"

    try:
        final_total = float(final_away_runs) + float(final_home_runs)
        total_line = float(total_line)
    except (TypeError, ValueError):
        return best_total_bet, None, "Ungraded", None, "invalid score entry"

    if best_total_bet == "Over":
        price = row.get("open_over_price", row.get("over_price", row.get("Over Price")))
        if final_total > total_line:
            units = american_odds_profit(price)
            if units is None:
                return best_total_bet, final_total, "Ungraded", None, "missing total price"
            return best_total_bet, final_total, "Win", units, None
        if final_total < total_line:
            return best_total_bet, final_total, "Loss", -1.0, None
        return best_total_bet, final_total, "Push", 0.0, None

    if best_total_bet == "Under":
        price = row.get("open_under_price", row.get("under_price", row.get("Under Price")))
        if final_total < total_line:
            units = american_odds_profit(price)
            if units is None:
                return best_total_bet, final_total, "Ungraded", None, "missing total price"
            return best_total_bet, final_total, "Win", units, None
        if final_total > total_line:
            return best_total_bet, final_total, "Loss", -1.0, None
        return best_total_bet, final_total, "Push", 0.0, None

    return best_total_bet, final_total, "Ungraded", None, "invalid total pick"


def auto_grade_tracked_bets() -> dict[str, int]:
    """Auto-grade tracked bets whose linked games now have final scores."""
    initialize_database()
    gradable_df = load_auto_gradable_tracked_bets()
    if gradable_df.empty:
        return {
            "eligible_rows": 0,
            "updated_rows": 0,
            "graded_rows": 0,
            "side_graded_rows": 0,
            "total_graded_rows": 0,
        }

    updated_rows = 0
    graded_rows = 0
    side_graded_rows = 0
    total_graded_rows = 0
    graded_timestamp = datetime.utcnow().isoformat()

    with get_connection() as connection:
        for _, row in gradable_df.iterrows():
            row_dict = row.to_dict()
            row_dict["final_away_runs"] = row_dict.get("game_away_score")
            row_dict["final_home_runs"] = row_dict.get("game_home_score")

            _, side_outcome, side_units, side_note = grade_side_pick_metrics(row_dict)
            _, _, total_outcome, total_units, total_note = grade_total_pick_metrics(row_dict)

            grading_note_parts = [note for note in [side_note, total_note] if note]
            grading_note = " | ".join(grading_note_parts) if grading_note_parts else None

            is_side_graded = side_outcome in {"Win", "Loss", "Push"}
            is_total_graded = total_outcome in {"Win", "Loss", "Push"}
            grading_status = "graded" if is_side_graded or is_total_graded else "ungraded"

            clv_side, clv_side_line_diff = calculate_side_clv_metrics(row_dict)
            clv_total, clv_total_line_diff = calculate_total_clv_metrics(row_dict)

            connection.execute(
                """
                UPDATE tracked_bets
                SET final_away_runs = COALESCE(?, final_away_runs),
                    final_home_runs = COALESCE(?, final_home_runs),
                    side_pick_outcome = COALESCE(?, side_pick_outcome),
                    total_pick_outcome = COALESCE(?, total_pick_outcome),
                    side_units = COALESCE(?, side_units),
                    total_units = COALESCE(?, total_units),
                    clv_side = COALESCE(?, clv_side),
                    clv_total = COALESCE(?, clv_total),
                    clv_side_line_diff = COALESCE(?, clv_side_line_diff),
                    clv_total_line_diff = COALESCE(?, clv_total_line_diff),
                    grading_status = ?,
                    grading_source = CASE WHEN ? = 'graded' THEN 'auto_db' ELSE grading_source END,
                    graded_timestamp = CASE WHEN ? = 'graded' THEN ? ELSE graded_timestamp END,
                    grading_note = COALESCE(?, grading_note),
                    updated_at = ?
                WHERE tracking_id = ?
                """,
                (
                    row_dict.get("final_away_runs"),
                    row_dict.get("final_home_runs"),
                    side_outcome if is_side_graded else None,
                    total_outcome if is_total_graded else None,
                    side_units,
                    total_units,
                    clv_side,
                    clv_total,
                    clv_side_line_diff,
                    clv_total_line_diff,
                    grading_status,
                    grading_status,
                    grading_status,
                    graded_timestamp,
                    grading_note,
                    graded_timestamp,
                    int(row["tracking_id"]),
                ),
            )
            updated_rows += 1
            if is_side_graded:
                side_graded_rows += 1
            if is_total_graded:
                total_graded_rows += 1
            if grading_status == "graded":
                graded_rows += 1

        connection.commit()

    return {
        "eligible_rows": int(len(gradable_df)),
        "updated_rows": updated_rows,
        "graded_rows": graded_rows,
        "side_graded_rows": side_graded_rows,
        "total_graded_rows": total_graded_rows,
    }


def sync_tracked_bets_with_odds_history(
    tracking_keys: list[str] | None = None,
    only_missing_open: bool = False,
    only_missing_close: bool = False,
) -> dict[str, int]:
    """
    Backfill tracked bets from historical odds snapshots.

    Opening lines use the earliest stored snapshot and closing lines use the
    latest stored snapshot for the linked game and sportsbook when available.
    """
    initialize_database()
    query = "SELECT * FROM tracked_bets WHERE game_id IS NOT NULL"
    params: list[Any] = []
    if tracking_keys:
        placeholders = ", ".join("?" for _ in tracking_keys)
        query += f" AND tracking_key IN ({placeholders})"
        params.extend(tracking_keys)

    with get_connection() as connection:
        tracked_bets_df = pd.read_sql_query(query, connection, params=params)

    if tracked_bets_df.empty:
        return {"eligible_rows": 0, "updated_rows": 0}

    game_ids = []
    for game_id in tracked_bets_df["game_id"].dropna().tolist():
        try:
            game_ids.append(int(game_id))
        except (TypeError, ValueError):
            continue
    history_lookup = load_odds_history_lookup(sorted(set(game_ids)))
    if not history_lookup["by_book"] and not history_lookup["overall"]:
        return {"eligible_rows": int(len(tracked_bets_df)), "updated_rows": 0}

    updated_rows = 0
    updated_at = datetime.utcnow().isoformat()
    with get_connection() as connection:
        for _, row in tracked_bets_df.iterrows():
            open_history_row = get_historical_market_row(
                history_lookup=history_lookup,
                game_id=row.get("game_id"),
                sportsbook_name=row.get("sportsbook"),
                side="open",
            )
            close_history_row = get_historical_market_row(
                history_lookup=history_lookup,
                game_id=row.get("game_id"),
                sportsbook_name=row.get("sportsbook"),
                side="close",
            )
            if open_history_row is None and close_history_row is None:
                continue

            current_row = row.to_dict()
            changed = False

            if open_history_row is not None:
                open_updates = {
                    "sportsbook": current_row.get("sportsbook") or open_history_row.get("sportsbook_name"),
                    "open_home_ml": open_history_row.get("home_moneyline"),
                    "open_away_ml": open_history_row.get("away_moneyline"),
                    "open_total": open_history_row.get("total_line"),
                    "open_over_price": open_history_row.get("over_price"),
                    "open_under_price": open_history_row.get("under_price"),
                    "market_timestamp_open": open_history_row.get("snapshot_time"),
                }
                for column_name, column_value in open_updates.items():
                    if only_missing_open and current_row.get(column_name) is not None and not pd.isna(current_row.get(column_name)):
                        continue
                    if column_value is None or pd.isna(column_value):
                        continue
                    if current_row.get(column_name) != column_value:
                        current_row[column_name] = column_value
                        changed = True

            if close_history_row is not None:
                close_updates = {
                    "sportsbook": current_row.get("sportsbook") or close_history_row.get("sportsbook_name"),
                    "close_home_ml": close_history_row.get("home_moneyline"),
                    "close_away_ml": close_history_row.get("away_moneyline"),
                    "close_total": close_history_row.get("total_line"),
                    "close_over_price": close_history_row.get("over_price"),
                    "close_under_price": close_history_row.get("under_price"),
                    "market_timestamp_close": close_history_row.get("snapshot_time"),
                }
                for column_name, column_value in close_updates.items():
                    if only_missing_close and current_row.get(column_name) is not None and not pd.isna(current_row.get(column_name)):
                        continue
                    if column_value is None or pd.isna(column_value):
                        continue
                    if current_row.get(column_name) != column_value:
                        current_row[column_name] = column_value
                        changed = True

            if not changed:
                continue

            clv_side, clv_side_line_diff = calculate_side_clv_metrics(current_row)
            clv_total, clv_total_line_diff = calculate_total_clv_metrics(current_row)

            connection.execute(
                """
                UPDATE tracked_bets
                SET sportsbook = ?,
                    open_home_ml = COALESCE(?, open_home_ml),
                    open_away_ml = COALESCE(?, open_away_ml),
                    open_total = COALESCE(?, open_total),
                    open_over_price = COALESCE(?, open_over_price),
                    open_under_price = COALESCE(?, open_under_price),
                    close_home_ml = COALESCE(?, close_home_ml),
                    close_away_ml = COALESCE(?, close_away_ml),
                    close_total = COALESCE(?, close_total),
                    close_over_price = COALESCE(?, close_over_price),
                    close_under_price = COALESCE(?, close_under_price),
                    market_timestamp_open = COALESCE(?, market_timestamp_open),
                    market_timestamp_close = COALESCE(?, market_timestamp_close),
                    clv_side = COALESCE(?, clv_side),
                    clv_total = COALESCE(?, clv_total),
                    clv_side_line_diff = COALESCE(?, clv_side_line_diff),
                    clv_total_line_diff = COALESCE(?, clv_total_line_diff),
                    updated_at = ?
                WHERE tracking_id = ?
                """,
                (
                    current_row.get("sportsbook"),
                    current_row.get("open_home_ml"),
                    current_row.get("open_away_ml"),
                    current_row.get("open_total"),
                    current_row.get("open_over_price"),
                    current_row.get("open_under_price"),
                    current_row.get("close_home_ml"),
                    current_row.get("close_away_ml"),
                    current_row.get("close_total"),
                    current_row.get("close_over_price"),
                    current_row.get("close_under_price"),
                    current_row.get("market_timestamp_open"),
                    current_row.get("market_timestamp_close"),
                    clv_side,
                    clv_total,
                    clv_side_line_diff,
                    clv_total_line_diff,
                    updated_at,
                    int(row["tracking_id"]),
                ),
            )
            updated_rows += 1

        connection.commit()

    return {"eligible_rows": int(len(tracked_bets_df)), "updated_rows": updated_rows}


def update_closing_lines(regions: str = DEFAULT_REGIONS) -> dict[str, int]:
    """
    Refresh close_* market fields for unresolved tracked bets and recalculate CLV.

    Returns a small status dictionary for logging or UI display.
    """
    initialize_database()
    unresolved_df = load_unresolved_tracked_bets()
    if unresolved_df.empty:
        return {"eligible_rows": 0, "updated_rows": 0, "matched_markets": 0, "historical_rows": 0}

    historical_results = sync_tracked_bets_with_odds_history(
        tracking_keys=unresolved_df["tracking_key"].dropna().astype(str).tolist(),
        only_missing_open=True,
        only_missing_close=False,
    )

    market_map = fetch_current_market_map(regions=regions)
    game_lookup = load_game_market_lookup()
    matched_markets = 0
    updated_rows = 0

    with get_connection() as connection:
        for _, row in unresolved_df.iterrows():
            game_id = row.get("game_id")
            matchup_key = None
            if game_id is not None and not pd.isna(game_id):
                try:
                    matchup_key = game_lookup.get(int(game_id))
                except (TypeError, ValueError):
                    matchup_key = None

            if matchup_key is None:
                matchup_key = (
                    normalize_team_name(row.get("away_team")),
                    normalize_team_name(row.get("home_team")),
                    str(row.get("snapshot_date", ""))[:10],
                )
            market_row = market_map.get(matchup_key)
            if market_row is None:
                continue

            matched_markets += 1
            updated_row = row.to_dict()
            updated_row["close_away_ml"] = market_row.get("away_moneyline")
            updated_row["close_home_ml"] = market_row.get("home_moneyline")
            updated_row["close_total"] = market_row.get("total_line")
            updated_row["close_over_price"] = market_row.get("over_price")
            updated_row["close_under_price"] = market_row.get("under_price")
            updated_row["market_timestamp_close"] = market_row.get("market_timestamp_close")
            if market_row.get("sportsbook"):
                updated_row["sportsbook"] = market_row["sportsbook"]

            clv_side, clv_side_line_diff = calculate_side_clv_metrics(updated_row)
            clv_total, clv_total_line_diff = calculate_total_clv_metrics(updated_row)

            connection.execute(
                """
                UPDATE tracked_bets
                SET sportsbook = ?,
                    close_away_ml = ?,
                    close_home_ml = ?,
                    close_total = ?,
                    close_over_price = ?,
                    close_under_price = ?,
                    clv_side = ?,
                    clv_total = ?,
                    clv_side_line_diff = ?,
                    clv_total_line_diff = ?,
                    market_timestamp_close = ?,
                    updated_at = ?
                WHERE tracking_id = ?
                """,
                (
                    updated_row.get("sportsbook"),
                    updated_row.get("close_away_ml"),
                    updated_row.get("close_home_ml"),
                    updated_row.get("close_total"),
                    updated_row.get("close_over_price"),
                    updated_row.get("close_under_price"),
                    clv_side,
                    clv_total,
                    clv_side_line_diff,
                    clv_total_line_diff,
                    updated_row.get("market_timestamp_close"),
                    datetime.utcnow().isoformat(),
                    int(row["tracking_id"]),
                ),
            )
            updated_rows += 1

        connection.commit()

    return {
        "eligible_rows": int(len(unresolved_df)),
        "updated_rows": updated_rows,
        "matched_markets": matched_markets,
        "historical_rows": historical_results["updated_rows"],
    }


def build_parser() -> argparse.ArgumentParser:
    """Build a small CLI parser for tracked-bet lifecycle helpers."""
    parser = argparse.ArgumentParser(
        description="Update tracked-bet closing lines or auto-grade completed games."
    )
    parser.add_argument(
        "--mode",
        choices=["close-lines", "grade"],
        default="close-lines",
        help="Choose whether to refresh close lines or auto-grade completed tracked bets.",
    )
    parser.add_argument(
        "--regions",
        default=DEFAULT_REGIONS,
        help="Odds API regions value. The default is 'us'.",
    )
    return parser


def main() -> None:
    """Run tracked-bet lifecycle maintenance from the command line."""
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "grade":
        results = auto_grade_tracked_bets()
        print(
            "Auto-graded "
            f"{results['graded_rows']} tracked bets "
            f"({results['side_graded_rows']} side results, {results['total_graded_rows']} total results, "
            f"{results['eligible_rows']} eligible rows)."
        )
        return

    results = update_closing_lines(regions=args.regions)
    print(
        "Updated closing lines for "
        f"{results['updated_rows']} tracked bets "
        f"({results['matched_markets']} matched live markets, "
        f"{results['historical_rows']} historical backfills, "
        f"{results['eligible_rows']} eligible rows)."
    )


if __name__ == "__main__":
    main()
