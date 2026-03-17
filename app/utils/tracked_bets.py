"""Tracked-bet persistence and reporting helpers for the Streamlit dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from db.connection import get_connection
from db.schema import initialize_database
from model.clv_tracker import (
    calculate_side_clv_metrics,
    calculate_total_clv_metrics,
    sync_tracked_bets_with_odds_history,
)


def normalize_team_name(team_name):
    """Normalize team names so snapshots, games, and odds rows can be matched."""
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
    return " ".join(tokens)


def build_tracking_key(snapshot_row):
    return (
        f"{snapshot_row.get('snapshot_timestamp', '')}|"
        f"{snapshot_row.get('snapshot_type', '')}|"
        f"{snapshot_row.get('Away', '')}|"
        f"{snapshot_row.get('Home', '')}"
    )


def build_grading_key(snapshot_row):
    return (
        f"{snapshot_row.get('snapshot_timestamp', '')}|"
        f"{snapshot_row.get('Away', '')}|"
        f"{snapshot_row.get('Home', '')}"
    )


@st.cache_data(show_spinner=False)
def load_game_tracking_lookup():
    """Load database games into a normalized lookup for tracked-bet matching."""
    initialize_database()
    query = """
        SELECT
            games.game_id,
            games.game_date,
            home_teams.team_name AS home_team_name,
            away_teams.team_name AS away_team_name
        FROM games
        JOIN teams AS home_teams ON games.home_team_id = home_teams.team_id
        JOIN teams AS away_teams ON games.away_team_id = away_teams.team_id
    """
    with get_connection() as connection:
        games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return []

    lookup_rows = []
    for _, row in games_df.iterrows():
        game_date_value = pd.to_datetime(row["game_date"], errors="coerce")
        if pd.isna(game_date_value):
            continue
        lookup_rows.append(
            {
                "game_id": int(row["game_id"]),
                "game_date": game_date_value.date(),
                "home_team_name": str(row["home_team_name"]),
                "away_team_name": str(row["away_team_name"]),
                "home_team_key": normalize_team_name(row["home_team_name"]),
                "away_team_key": normalize_team_name(row["away_team_name"]),
            }
        )

    return lookup_rows


@st.cache_data(show_spinner=False)
def load_game_results_lookup():
    """Load final-score game results keyed by game_id for tracked-bet grading."""
    initialize_database()
    query = """
        SELECT
            game_id,
            status,
            home_score,
            away_score
        FROM games
    """
    with get_connection() as connection:
        games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return {}

    results_lookup = {}
    for _, row in games_df.iterrows():
        try:
            game_id = int(row["game_id"])
        except (TypeError, ValueError):
            continue
        results_lookup[game_id] = {
            "status": row.get("status"),
            "home_score": row.get("home_score"),
            "away_score": row.get("away_score"),
        }
    return results_lookup


@st.cache_data(show_spinner=False)
def load_tracked_bets_from_db():
    initialize_database()
    with get_connection() as connection:
        return pd.read_sql_query(
            "SELECT * FROM tracked_bets ORDER BY snapshot_timestamp DESC, tracking_id DESC",
            connection,
        )


def clear_tracked_bet_caches():
    """Clear cached tracked-bet lookups after DB updates."""
    load_game_tracking_lookup.clear()
    load_game_results_lookup.clear()
    load_tracked_bets_from_db.clear()


def match_snapshot_row_to_game(snapshot_row, game_lookup_rows):
    """
    Match a tracked-bet snapshot row to one database game.

    Matching is conservative:
    - exact snapshot date first
    - if no match, allow +/- 1 day
    - only auto-link when there is exactly one candidate
    """
    away_team_key = normalize_team_name(snapshot_row.get("Away"))
    home_team_key = normalize_team_name(snapshot_row.get("Home"))
    snapshot_date_text = str(snapshot_row.get("snapshot_date", "")).strip()

    try:
        snapshot_date_value = pd.to_datetime(snapshot_date_text, errors="coerce")
    except Exception:
        snapshot_date_value = pd.NaT

    if not away_team_key or not home_team_key or pd.isna(snapshot_date_value):
        return None, "unmatched"

    snapshot_date = snapshot_date_value.date()
    team_matches = [
        row
        for row in game_lookup_rows
        if row["away_team_key"] == away_team_key and row["home_team_key"] == home_team_key
    ]
    if not team_matches:
        return None, "unmatched"

    exact_matches = [row for row in team_matches if row["game_date"] == snapshot_date]
    if len(exact_matches) == 1:
        return exact_matches[0]["game_id"], "exact_date"
    if len(exact_matches) > 1:
        return None, "ambiguous"

    adjacent_dates = {
        snapshot_date - timedelta(days=1),
        snapshot_date + timedelta(days=1),
    }
    adjacent_matches = [row for row in team_matches if row["game_date"] in adjacent_dates]
    if len(adjacent_matches) == 1:
        return adjacent_matches[0]["game_id"], "adjacent_date"
    if len(adjacent_matches) > 1:
        return None, "ambiguous"

    return None, "unmatched"


def persist_snapshot_rows_to_db(snapshot_df):
    """
    Persist dashboard snapshot rows into SQLite for later CLV and grading updates.

    The CSV snapshot files remain in place for the existing workflow, while the
    database becomes the source of truth for open/close market tracking.
    """
    if snapshot_df is None or snapshot_df.empty:
        return 0

    initialize_database()
    game_lookup_rows = load_game_tracking_lookup()
    persisted_rows = []
    for _, row in snapshot_df.iterrows():
        row_dict = row.to_dict()
        matched_game_id, game_match_method = match_snapshot_row_to_game(row_dict, game_lookup_rows)
        persisted_rows.append(
            {
                "tracking_key": build_tracking_key(row_dict),
                "grading_key": build_grading_key(row_dict),
                "game_id": matched_game_id,
                "game_match_method": game_match_method,
                "snapshot_timestamp": row_dict.get("snapshot_timestamp"),
                "snapshot_date": row_dict.get("snapshot_date"),
                "snapshot_type": row_dict.get("snapshot_type"),
                "data_mode": row_dict.get("data_mode"),
                "run_dispersion": row_dict.get("run_dispersion"),
                "away_team": row_dict.get("Away"),
                "home_team": row_dict.get("Home"),
                "sportsbook": row_dict.get("Sportsbook"),
                "best_bet": row_dict.get("Best Bet"),
                "bet_flag": row_dict.get("Bet Flag"),
                "best_total_bet": row_dict.get("Best Total Bet"),
                "total_bet_flag": row_dict.get("Total Bet Flag"),
                "away_moneyline": row_dict.get("Away Moneyline"),
                "home_moneyline": row_dict.get("Home Moneyline"),
                "total_line": row_dict.get("Total Line"),
                "over_price": row_dict.get("Over Price"),
                "under_price": row_dict.get("Under Price"),
                "open_home_ml": row_dict.get("Home Moneyline"),
                "open_away_ml": row_dict.get("Away Moneyline"),
                "open_total": row_dict.get("Total Line"),
                "open_over_price": row_dict.get("Over Price"),
                "open_under_price": row_dict.get("Under Price"),
                "market_timestamp_open": row_dict.get("snapshot_timestamp"),
                "grading_status": row_dict.get("grading_status", "ungraded"),
                "updated_at": datetime.utcnow().isoformat(),
            }
        )

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO tracked_bets (
                tracking_key,
                grading_key,
                game_id,
                game_match_method,
                snapshot_timestamp,
                snapshot_date,
                snapshot_type,
                data_mode,
                run_dispersion,
                away_team,
                home_team,
                sportsbook,
                best_bet,
                bet_flag,
                best_total_bet,
                total_bet_flag,
                away_moneyline,
                home_moneyline,
                total_line,
                over_price,
                under_price,
                open_home_ml,
                open_away_ml,
                open_total,
                open_over_price,
                open_under_price,
                market_timestamp_open,
                grading_status,
                updated_at
            )
            VALUES (
                :tracking_key,
                :grading_key,
                :game_id,
                :game_match_method,
                :snapshot_timestamp,
                :snapshot_date,
                :snapshot_type,
                :data_mode,
                :run_dispersion,
                :away_team,
                :home_team,
                :sportsbook,
                :best_bet,
                :bet_flag,
                :best_total_bet,
                :total_bet_flag,
                :away_moneyline,
                :home_moneyline,
                :total_line,
                :over_price,
                :under_price,
                :open_home_ml,
                :open_away_ml,
                :open_total,
                :open_over_price,
                :open_under_price,
                :market_timestamp_open,
                :grading_status,
                :updated_at
            )
            ON CONFLICT(tracking_key) DO UPDATE SET
                game_id = COALESCE(tracked_bets.game_id, excluded.game_id),
                game_match_method = CASE
                    WHEN tracked_bets.game_id IS NULL THEN excluded.game_match_method
                    ELSE tracked_bets.game_match_method
                END,
                sportsbook = excluded.sportsbook,
                best_bet = excluded.best_bet,
                bet_flag = excluded.bet_flag,
                best_total_bet = excluded.best_total_bet,
                total_bet_flag = excluded.total_bet_flag,
                away_moneyline = excluded.away_moneyline,
                home_moneyline = excluded.home_moneyline,
                total_line = excluded.total_line,
                over_price = excluded.over_price,
                under_price = excluded.under_price,
                open_home_ml = COALESCE(tracked_bets.open_home_ml, excluded.open_home_ml),
                open_away_ml = COALESCE(tracked_bets.open_away_ml, excluded.open_away_ml),
                open_total = COALESCE(tracked_bets.open_total, excluded.open_total),
                open_over_price = COALESCE(tracked_bets.open_over_price, excluded.open_over_price),
                open_under_price = COALESCE(tracked_bets.open_under_price, excluded.open_under_price),
                market_timestamp_open = COALESCE(tracked_bets.market_timestamp_open, excluded.market_timestamp_open),
                updated_at = excluded.updated_at
            """,
            persisted_rows,
        )
        connection.commit()

    tracking_keys = [row["tracking_key"] for row in persisted_rows if row.get("tracking_key")]
    if tracking_keys:
        sync_tracked_bets_with_odds_history(
            tracking_keys=tracking_keys,
            only_missing_open=False,
            only_missing_close=True,
        )

    load_tracked_bets_from_db.clear()
    return len(persisted_rows)


def build_graded_results_from_tracked_bets(tracked_bets_df):
    """Normalize graded tracked-bet rows into the reporting dataframe shape."""
    if tracked_bets_df is None or tracked_bets_df.empty:
        return pd.DataFrame()

    graded_df = tracked_bets_df[
        tracked_bets_df["grading_status"].fillna("").eq("graded")
    ].copy()
    if graded_df.empty:
        return pd.DataFrame()

    normalized_df = pd.DataFrame(
        {
            "grading_key": graded_df.get("grading_key"),
            "snapshot_timestamp": graded_df.get("snapshot_timestamp"),
            "Away": graded_df.get("away_team"),
            "Home": graded_df.get("home_team"),
            "Best Bet": graded_df.get("best_bet"),
            "Bet Flag": graded_df.get("bet_flag"),
            "Best Total Bet": graded_df.get("best_total_bet"),
            "Total Bet Flag": graded_df.get("total_bet_flag"),
            "Away Moneyline": graded_df.get("open_away_ml").where(
                graded_df.get("open_away_ml").notna(),
                graded_df.get("away_moneyline"),
            ),
            "Home Moneyline": graded_df.get("open_home_ml").where(
                graded_df.get("open_home_ml").notna(),
                graded_df.get("home_moneyline"),
            ),
            "Total Line": graded_df.get("open_total").where(
                graded_df.get("open_total").notna(),
                graded_df.get("total_line"),
            ),
            "Over Price": graded_df.get("open_over_price").where(
                graded_df.get("open_over_price").notna(),
                graded_df.get("over_price"),
            ),
            "Under Price": graded_df.get("open_under_price").where(
                graded_df.get("open_under_price").notna(),
                graded_df.get("under_price"),
            ),
            "Closing Away Moneyline": graded_df.get("close_away_ml"),
            "Closing Home Moneyline": graded_df.get("close_home_ml"),
            "Closing Total Line": graded_df.get("close_total"),
            "Closing Over Price": graded_df.get("close_over_price"),
            "Closing Under Price": graded_df.get("close_under_price"),
            "Final Away Runs": graded_df.get("final_away_runs"),
            "Final Home Runs": graded_df.get("final_home_runs"),
            "Side Pick Outcome": graded_df.get("side_pick_outcome"),
            "Total Pick Outcome": graded_df.get("total_pick_outcome"),
            "Side Units": graded_df.get("side_units"),
            "Total Units": graded_df.get("total_units"),
            "Side CLV": graded_df.get("clv_side"),
            "Total CLV": graded_df.get("clv_total"),
            "grading_note": graded_df.get("grading_note"),
            "grading_status": graded_df.get("grading_status"),
            "graded_timestamp": graded_df.get("graded_timestamp"),
            "game_id": graded_df.get("game_id"),
        }
    )
    return normalized_df


def enrich_snapshot_with_tracked_bets(snapshot_df):
    """Overlay any tracked open/close market data onto a loaded CSV snapshot."""
    tracked_bets_df = load_tracked_bets_from_db()
    if snapshot_df is None or snapshot_df.empty or tracked_bets_df.empty:
        return snapshot_df

    snapshot_copy = snapshot_df.copy()
    game_lookup_rows = load_game_tracking_lookup()
    game_results_lookup = load_game_results_lookup()
    snapshot_copy["grading_key"] = snapshot_copy.apply(build_grading_key, axis=1)
    if "game_id" not in snapshot_copy.columns:
        match_results = snapshot_copy.apply(
            lambda row: match_snapshot_row_to_game(row, game_lookup_rows),
            axis=1,
        )
        snapshot_copy["game_id"] = match_results.apply(lambda result: result[0] if isinstance(result, tuple) else None)
        snapshot_copy["game_match_method"] = match_results.apply(
            lambda result: result[1] if isinstance(result, tuple) else "unmatched"
        )

    tracked_subset = tracked_bets_df[
        [
            "grading_key",
            "game_id",
            "game_match_method",
            "open_home_ml",
            "open_away_ml",
            "open_total",
            "open_over_price",
            "open_under_price",
            "close_home_ml",
            "close_away_ml",
            "close_total",
            "close_over_price",
            "close_under_price",
            "market_timestamp_open",
            "market_timestamp_close",
            "clv_side",
            "clv_total",
            "final_away_runs",
            "final_home_runs",
        ]
    ].drop_duplicates(subset=["grading_key"], keep="last")

    merged_df = snapshot_copy.merge(tracked_subset, on="grading_key", how="left")
    if "game_id_x" in merged_df.columns and "game_id_y" in merged_df.columns:
        merged_df["game_id"] = merged_df["game_id_x"].where(merged_df["game_id_x"].notna(), merged_df["game_id_y"])
        merged_df = merged_df.drop(columns=["game_id_x", "game_id_y"])
    elif "game_id_y" in merged_df.columns:
        merged_df = merged_df.rename(columns={"game_id_y": "game_id"})
    elif "game_id_x" in merged_df.columns:
        merged_df = merged_df.rename(columns={"game_id_x": "game_id"})

    if "game_match_method_x" in merged_df.columns and "game_match_method_y" in merged_df.columns:
        merged_df["game_match_method"] = merged_df["game_match_method_x"].where(
            merged_df["game_match_method_x"].notna(),
            merged_df["game_match_method_y"],
        )
        merged_df = merged_df.drop(columns=["game_match_method_x", "game_match_method_y"])
    elif "game_match_method_y" in merged_df.columns:
        merged_df = merged_df.rename(columns={"game_match_method_y": "game_match_method"})
    elif "game_match_method_x" in merged_df.columns:
        merged_df = merged_df.rename(columns={"game_match_method_x": "game_match_method"})

    if "Home Moneyline" in merged_df.columns:
        merged_df["Home Moneyline"] = merged_df["Home Moneyline"].fillna(merged_df["open_home_ml"])
    if "Away Moneyline" in merged_df.columns:
        merged_df["Away Moneyline"] = merged_df["Away Moneyline"].fillna(merged_df["open_away_ml"])
    if "Total Line" in merged_df.columns:
        merged_df["Total Line"] = merged_df["Total Line"].fillna(merged_df["open_total"])
    if "Over Price" in merged_df.columns:
        merged_df["Over Price"] = merged_df["Over Price"].fillna(merged_df["open_over_price"])
    if "Under Price" in merged_df.columns:
        merged_df["Under Price"] = merged_df["Under Price"].fillna(merged_df["open_under_price"])

    if "Closing Away Moneyline" in merged_df.columns:
        merged_df["Closing Away Moneyline"] = merged_df["Closing Away Moneyline"].fillna(merged_df["close_away_ml"])
    else:
        merged_df["Closing Away Moneyline"] = merged_df["close_away_ml"]
    if "Closing Home Moneyline" in merged_df.columns:
        merged_df["Closing Home Moneyline"] = merged_df["Closing Home Moneyline"].fillna(merged_df["close_home_ml"])
    else:
        merged_df["Closing Home Moneyline"] = merged_df["close_home_ml"]
    if "Closing Total Line" in merged_df.columns:
        merged_df["Closing Total Line"] = merged_df["Closing Total Line"].fillna(merged_df["close_total"])
    else:
        merged_df["Closing Total Line"] = merged_df["close_total"]
    if "Closing Over Price" in merged_df.columns:
        merged_df["Closing Over Price"] = merged_df["Closing Over Price"].fillna(merged_df["close_over_price"])
    else:
        merged_df["Closing Over Price"] = merged_df["close_over_price"]
    if "Closing Under Price" in merged_df.columns:
        merged_df["Closing Under Price"] = merged_df["Closing Under Price"].fillna(merged_df["close_under_price"])
    else:
        merged_df["Closing Under Price"] = merged_df["close_under_price"]

    if "Final Away Runs" in merged_df.columns:
        merged_df["Final Away Runs"] = merged_df["Final Away Runs"].fillna(merged_df["final_away_runs"])
    else:
        merged_df["Final Away Runs"] = merged_df["final_away_runs"]
    if "Final Home Runs" in merged_df.columns:
        merged_df["Final Home Runs"] = merged_df["Final Home Runs"].fillna(merged_df["final_home_runs"])
    else:
        merged_df["Final Home Runs"] = merged_df["final_home_runs"]

    if "game_id" in merged_df.columns:
        for idx, row in merged_df.iterrows():
            game_id = row.get("game_id")
            if game_id is None or pd.isna(game_id):
                continue
            try:
                game_result = game_results_lookup.get(int(game_id))
            except (TypeError, ValueError):
                game_result = None
            if not game_result:
                continue
            if pd.isna(merged_df.at[idx, "Final Away Runs"]):
                merged_df.at[idx, "Final Away Runs"] = game_result.get("away_score")
            if pd.isna(merged_df.at[idx, "Final Home Runs"]):
                merged_df.at[idx, "Final Home Runs"] = game_result.get("home_score")

    return merged_df


def sync_graded_results_to_db(graded_rows_df):
    """Update tracked_bets rows with closing lines, grading outcomes, and CLV."""
    if graded_rows_df is None or graded_rows_df.empty:
        return 0

    initialize_database()
    updated_count = 0
    with get_connection() as connection:
        for _, row in graded_rows_df.iterrows():
            grading_key = row.get("grading_key")
            game_id = row.get("game_id")
            if not grading_key and (game_id is None or pd.isna(game_id)):
                continue

            row_dict = row.to_dict()
            side_clv, side_line_diff = calculate_side_clv_metrics(
                {
                    "best_bet": row_dict.get("Best Bet"),
                    "away_team": row_dict.get("Away"),
                    "home_team": row_dict.get("Home"),
                    "open_away_ml": row_dict.get("Away Moneyline"),
                    "open_home_ml": row_dict.get("Home Moneyline"),
                    "close_away_ml": row_dict.get("Closing Away Moneyline"),
                    "close_home_ml": row_dict.get("Closing Home Moneyline"),
                }
            )
            total_clv, total_line_diff = calculate_total_clv_metrics(
                {
                    "best_total_bet": row_dict.get("Best Total Bet"),
                    "open_total": row_dict.get("Total Line"),
                    "close_total": row_dict.get("Closing Total Line"),
                    "open_over_price": row_dict.get("Over Price"),
                    "open_under_price": row_dict.get("Under Price"),
                    "close_over_price": row_dict.get("Closing Over Price"),
                    "close_under_price": row_dict.get("Closing Under Price"),
                }
            )

            update_sql = """
                UPDATE tracked_bets
                SET close_away_ml = COALESCE(?, close_away_ml),
                    close_home_ml = COALESCE(?, close_home_ml),
                    close_total = COALESCE(?, close_total),
                    close_over_price = COALESCE(?, close_over_price),
                    close_under_price = COALESCE(?, close_under_price),
                    clv_side = COALESCE(?, clv_side),
                    clv_total = COALESCE(?, clv_total),
                    clv_side_line_diff = COALESCE(?, clv_side_line_diff),
                    clv_total_line_diff = COALESCE(?, clv_total_line_diff),
                    market_timestamp_close = COALESCE(?, market_timestamp_close),
                    final_away_runs = COALESCE(?, final_away_runs),
                    final_home_runs = COALESCE(?, final_home_runs),
                    side_pick_outcome = COALESCE(?, side_pick_outcome),
                    total_pick_outcome = COALESCE(?, total_pick_outcome),
                    side_units = COALESCE(?, side_units),
                    total_units = COALESCE(?, total_units),
                    grading_status = COALESCE(?, grading_status),
                    grading_source = COALESCE(?, grading_source),
                    graded_timestamp = COALESCE(?, graded_timestamp),
                    grading_note = COALESCE(?, grading_note),
                    updated_at = ?
            """
            update_params = (
                row_dict.get("Closing Away Moneyline"),
                row_dict.get("Closing Home Moneyline"),
                row_dict.get("Closing Total Line"),
                row_dict.get("Closing Over Price"),
                row_dict.get("Closing Under Price"),
                side_clv,
                total_clv,
                side_line_diff,
                total_line_diff,
                row_dict.get("market_timestamp_close"),
                row_dict.get("Final Away Runs"),
                row_dict.get("Final Home Runs"),
                row_dict.get("Side Pick Outcome"),
                row_dict.get("Total Pick Outcome"),
                row_dict.get("Side Units"),
                row_dict.get("Total Units"),
                row_dict.get("grading_status"),
                "manual_snapshot" if row_dict.get("grading_status") == "graded" else None,
                row_dict.get("graded_timestamp"),
                row_dict.get("grading_note"),
                datetime.utcnow().isoformat(),
            )

            cursor = None
            if grading_key:
                cursor = connection.execute(
                    f"{update_sql} WHERE grading_key = ?",
                    update_params + (grading_key,),
                )

            if (cursor is None or cursor.rowcount == 0) and game_id is not None and not pd.isna(game_id):
                try:
                    cursor = connection.execute(
                        f"{update_sql} WHERE game_id = ? AND grading_key IS NULL",
                        update_params + (int(game_id),),
                    )
                except (TypeError, ValueError):
                    cursor = None

            if cursor is not None and cursor.rowcount > 0:
                updated_count += cursor.rowcount

        connection.commit()

    load_tracked_bets_from_db.clear()
    return updated_count


def build_tracked_bet_lifecycle_records(tracked_bets_df):
    """Normalize tracked bets into a compact lifecycle-monitoring dataframe."""
    if tracked_bets_df is None or tracked_bets_df.empty:
        return pd.DataFrame()

    lifecycle_df = tracked_bets_df.copy()
    lifecycle_df["Snapshot"] = pd.to_datetime(
        lifecycle_df.get("snapshot_timestamp"),
        errors="coerce",
    )
    lifecycle_df["Matchup"] = lifecycle_df.apply(
        lambda row: f"{row.get('away_team', 'Away')} at {row.get('home_team', 'Home')}",
        axis=1,
    )
    lifecycle_df["Has Bet"] = lifecycle_df.apply(
        lambda row: (
            row.get("bet_flag") in {"Lean", "Strong Bet"}
            or row.get("total_bet_flag") in {"Lean", "Strong Bet"}
        ),
        axis=1,
    )
    lifecycle_df["Linked"] = lifecycle_df["game_id"].notna()
    lifecycle_df["Has Final Score"] = (
        lifecycle_df.get("final_away_runs").notna()
        & lifecycle_df.get("final_home_runs").notna()
    )
    lifecycle_df["Has Close Lines"] = (
        lifecycle_df.get("market_timestamp_close").notna()
        | lifecycle_df.get("close_home_ml").notna()
        | lifecycle_df.get("close_away_ml").notna()
        | lifecycle_df.get("close_total").notna()
    )
    lifecycle_df["Needs Link"] = lifecycle_df["Has Bet"] & ~lifecycle_df["Linked"]
    lifecycle_df["Eligible For Auto Grade"] = (
        lifecycle_df["Has Bet"]
        & lifecycle_df["Linked"]
        & lifecycle_df["Has Final Score"]
        & ~lifecycle_df.get("grading_status", pd.Series(dtype="object")).fillna("").eq("graded")
    )
    lifecycle_df["Resolved"] = lifecycle_df.get("grading_status", pd.Series(dtype="object")).fillna("").eq("graded")
    lifecycle_df["Grade Source"] = lifecycle_df.get("grading_source").fillna("Pending")
    lifecycle_df["Close Status"] = lifecycle_df["Has Close Lines"].map({True: "Captured", False: "Pending"})
    lifecycle_df["Link Status"] = lifecycle_df["Linked"].map({True: "Linked", False: "Unlinked"})
    lifecycle_df["Lifecycle Status"] = lifecycle_df.apply(
        lambda row: (
            "Needs Link"
            if row["Needs Link"]
            else "Ready To Grade"
            if row["Eligible For Auto Grade"]
            else "Graded"
            if row["Resolved"]
            else "Awaiting Result"
        ),
        axis=1,
    )
    lifecycle_df = lifecycle_df.sort_values(by=["Snapshot"], ascending=[False]).reset_index(drop=True)
    return lifecycle_df


def summarize_tracked_bet_lifecycle(lifecycle_df):
    """Return compact tracked-bet lifecycle metrics for the performance dashboard."""
    if lifecycle_df is None or lifecycle_df.empty:
        return None

    actionable_df = lifecycle_df[lifecycle_df["Has Bet"]].copy()
    if actionable_df.empty:
        return None

    recent_df = actionable_df[
        [
            "Snapshot",
            "Matchup",
            "Link Status",
            "Close Status",
            "Lifecycle Status",
            "Grade Source",
            "game_match_method",
        ]
    ].head(20).copy()

    source_summary_df = (
        actionable_df[actionable_df["Resolved"]]
        .groupby("Grade Source")
        .size()
        .reset_index(name="Bets")
        if actionable_df["Resolved"].any()
        else pd.DataFrame(columns=["Grade Source", "Bets"])
    )

    return {
        "tracked_bets": int(len(actionable_df)),
        "linked_bets": int(actionable_df["Linked"].sum()),
        "unlinked_bets": int(actionable_df["Needs Link"].sum()),
        "close_captured": int(actionable_df["Has Close Lines"].sum()),
        "eligible_for_auto_grade": int(actionable_df["Eligible For Auto Grade"].sum()),
        "graded_bets": int(actionable_df["Resolved"].sum()),
        "auto_graded_bets": int(actionable_df["Grade Source"].eq("auto_db").sum()),
        "manual_graded_bets": int(actionable_df["Grade Source"].eq("manual_snapshot").sum()),
        "recent_lifecycle": recent_df,
        "grade_source_summary": source_summary_df,
    }


def build_clv_market_records(tracked_bets_df):
    """Normalize tracked side and total CLV rows into one reporting dataframe."""
    if tracked_bets_df is None or tracked_bets_df.empty:
        return pd.DataFrame()

    records = []
    for _, row in tracked_bets_df.iterrows():
        matchup_label = f"{row.get('away_team', 'Away')} at {row.get('home_team', 'Home')}"
        closed_at = row.get("market_timestamp_close") or row.get("graded_timestamp") or row.get("snapshot_timestamp")

        side_clv = row.get("clv_side")
        if (
            row.get("bet_flag") in {"Lean", "Strong Bet"}
            and row.get("best_bet") not in {None, "Pass"}
            and side_clv is not None
            and not pd.isna(side_clv)
        ):
            records.append(
                {
                    "Closed": closed_at,
                    "Matchup": matchup_label,
                    "Market Type": "Side",
                    "Pick": row.get("best_bet"),
                    "CLV": float(side_clv),
                    "Beat Close": float(side_clv) > 0,
                }
            )

        total_clv = row.get("clv_total")
        if (
            row.get("total_bet_flag") in {"Lean", "Strong Bet"}
            and row.get("best_total_bet") not in {None, "Pass"}
            and total_clv is not None
            and not pd.isna(total_clv)
        ):
            records.append(
                {
                    "Closed": closed_at,
                    "Matchup": matchup_label,
                    "Market Type": "Total",
                    "Pick": row.get("best_total_bet"),
                    "CLV": float(total_clv),
                    "Beat Close": float(total_clv) > 0,
                }
            )

    if not records:
        return pd.DataFrame()

    clv_records_df = pd.DataFrame(records)
    clv_records_df["Closed"] = pd.to_datetime(clv_records_df["Closed"], errors="coerce")
    clv_records_df = clv_records_df.sort_values(by=["Closed"], ascending=[False]).reset_index(drop=True)
    return clv_records_df


def summarize_clv_records(clv_records_df):
    """Return compact CLV summary metrics for the performance dashboard."""
    if clv_records_df is None or clv_records_df.empty:
        return None

    side_df = clv_records_df[clv_records_df["Market Type"] == "Side"].copy()
    total_df = clv_records_df[clv_records_df["Market Type"] == "Total"].copy()

    return {
        "avg_side_clv": side_df["CLV"].mean() if not side_df.empty else None,
        "avg_total_clv": total_df["CLV"].mean() if not total_df.empty else None,
        "beat_close_pct": clv_records_df["Beat Close"].mean() * 100.0 if not clv_records_df.empty else None,
        "side_beat_close_pct": side_df["Beat Close"].mean() * 100.0 if not side_df.empty else None,
        "total_beat_close_pct": total_df["Beat Close"].mean() * 100.0 if not total_df.empty else None,
        "market_type_summary": (
            clv_records_df.groupby("Market Type")
            .agg(
                Bets=("CLV", "count"),
                Avg_CLV=("CLV", "mean"),
                Beat_Close_Rate=("Beat Close", "mean"),
            )
            .reset_index()
        ),
        "recent_20": clv_records_df.head(20).copy(),
    }
