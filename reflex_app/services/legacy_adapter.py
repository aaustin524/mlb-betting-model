"""Thin Reflex adapter over the shared board services.

This module intentionally avoids re-implementing board business logic.
It only adds Reflex-specific integration concerns such as:
- lightweight local caching
- optional database odds fallback
- conversion from shared pandas outputs into UI-friendly plain structures
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

import pandas as pd

from app.db.connection import get_connection
from app.services.board_data import (
    INPUT_COLUMNS,
    TABLE_COLUMNS,
    build_daily_input_table,
    build_display_dataframe,
    build_summary_metrics,
    build_top_plays_dataframe,
    format_moneyline,
    load_lineup_data_frames,
    load_matchups_data,
    load_pitcher_ratings_data,
)
from model.team_loader import load_team_ratings
from model.weather_api import load_stadium_locations
from project_config import DB_PATH
from reflex_app.services.live_odds import get_board_h2h_odds, normalize_team_name
from reflex_app.services.team_branding import get_team_branding, get_team_logo_src
from reflex_app.services.ui_formatters import (
    format_matchup_label,
    format_matchup_probability_line,
    format_signal_label,
)


def get_selected_slate_date(matchups: pd.DataFrame) -> str | None:
    """Return the schedule date for the current Reflex board slate."""
    if matchups.empty or "game_date" not in matchups.columns:
        return None

    game_dates = matchups["game_date"].dropna().astype(str)
    if game_dates.empty:
        return None
    return game_dates.iloc[0][:10]


@lru_cache(maxsize=1)
def load_core_inputs() -> dict[str, pd.DataFrame]:
    """Load board inputs once for the Reflex service layer."""
    team_ratings = load_team_ratings("data/teams.csv")
    pitcher_ratings = load_pitcher_ratings_data("data/pitcher_ratings.csv")
    stadium_locations = load_stadium_locations(data_mode="local")
    hitter_ratings, projected_lineups = load_lineup_data_frames()
    matchups = load_matchups_data(data_mode="live")
    return {
        "team_ratings": team_ratings,
        "pitcher_ratings": pitcher_ratings,
        "stadium_locations": stadium_locations,
        "hitter_ratings": hitter_ratings,
        "projected_lineups": projected_lineups,
        "matchups": matchups,
    }


def clear_caches() -> None:
    """Reset Reflex-side caches without affecting core service behavior."""
    load_core_inputs.cache_clear()
    load_latest_odds_rows.cache_clear()


@lru_cache(maxsize=1)
def load_latest_odds_rows() -> pd.DataFrame:
    """Load latest saved odds rows for Reflex-only market fallback."""
    if not DB_PATH.exists():
        return pd.DataFrame()

    query = """
        WITH ranked AS (
            SELECT
                g.game_date,
                away.team_name AS away_team,
                home.team_name AS home_team,
                o.sportsbook_name,
                o.away_moneyline,
                o.home_moneyline,
                o.total_line,
                o.over_price,
                o.under_price,
                o.snapshot_time,
                ROW_NUMBER() OVER (
                    PARTITION BY away.team_name, home.team_name
                    ORDER BY o.snapshot_time DESC
                ) AS row_num
            FROM odds_snapshots o
            JOIN games g ON g.game_id = o.game_id
            JOIN teams away ON away.team_id = g.away_team_id
            JOIN teams home ON home.team_id = g.home_team_id
        )
        SELECT
            game_date,
            away_team,
            home_team,
            sportsbook_name,
            away_moneyline,
            home_moneyline,
            total_line,
            over_price,
            under_price,
            snapshot_time
        FROM ranked
        WHERE row_num = 1
    """
    with sqlite3.connect(DB_PATH) as connection:
        return pd.read_sql_query(query, connection)


def load_board_market_context(
    inputs: dict[str, pd.DataFrame],
    force_refresh: bool = False,
) -> tuple[dict[tuple[str, str], dict[str, object]], dict[str, object]]:
    """Load quota-aware board odds plus metadata for UI status and refresh rules."""
    market_lookup, odds_status = get_board_h2h_odds(
        inputs["matchups"],
        force_refresh=force_refresh,
    )
    return market_lookup, odds_status


def build_reflex_daily_input_table(
    inputs: dict[str, pd.DataFrame],
    live_odds_market_data: dict[tuple[str, str], dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Build the shared daily input table with live odds applied to the live slate."""
    board_df = build_daily_input_table(
        matchups=inputs["matchups"],
        pitcher_ratings=inputs["pitcher_ratings"],
        stadium_locations=inputs["stadium_locations"],
        hitter_ratings=inputs["hitter_ratings"],
        projected_lineups=inputs["projected_lineups"],
        team_ratings=inputs["team_ratings"],
        data_mode="live",
    )

    market_lookup = live_odds_market_data or load_board_market_context(inputs)[0]
    updated_df = board_df.copy()
    for idx, row in updated_df.iterrows():
        market_row = market_lookup.get(
            (
                normalize_team_name(str(row["Away"])),
                normalize_team_name(str(row["Home"])),
            )
        )
        if market_row is None:
            continue

        updated_df.at[idx, "Away Moneyline"] = market_row.get("away_moneyline")
        updated_df.at[idx, "Home Moneyline"] = market_row.get("home_moneyline")
        updated_df.at[idx, "Total Line"] = market_row.get("total_line")
        updated_df.at[idx, "Over Price"] = market_row.get("over_price")
        updated_df.at[idx, "Under Price"] = market_row.get("under_price")
        updated_df.at[idx, "Sportsbook"] = market_row.get("sportsbook")
        updated_df.at[idx, "Bookmaker Key"] = market_row.get("bookmaker_key")
        updated_df.at[idx, "Event Id"] = market_row.get("event_id")
        updated_df.at[idx, "Sport Key"] = market_row.get("sport_key")
        updated_df.at[idx, "Commence Time"] = market_row.get("commence_time")

    unmatched_mask = updated_df["Away Moneyline"].isna() | updated_df["Home Moneyline"].isna()
    if unmatched_mask.any():
        odds_df = load_latest_odds_rows()
        if not odds_df.empty:
            odds_lookup = {
                (
                    normalize_team_name(str(row["away_team"])),
                    normalize_team_name(str(row["home_team"])),
                ): row.to_dict()
                for _, row in odds_df.iterrows()
            }

            for idx, row in updated_df.loc[unmatched_mask].iterrows():
                odds_row = odds_lookup.get(
                    (
                        normalize_team_name(str(row["Away"])),
                        normalize_team_name(str(row["Home"])),
                    )
                )
                if odds_row is None:
                    continue

                updated_df.at[idx, "Away Moneyline"] = odds_row.get("away_moneyline")
                updated_df.at[idx, "Home Moneyline"] = odds_row.get("home_moneyline")
                updated_df.at[idx, "Total Line"] = odds_row.get("total_line")
                updated_df.at[idx, "Over Price"] = odds_row.get("over_price")
                updated_df.at[idx, "Under Price"] = odds_row.get("under_price")
                updated_df.at[idx, "Sportsbook"] = odds_row.get("sportsbook_name")
                updated_df.at[idx, "Bookmaker Key"] = None
                updated_df.at[idx, "Event Id"] = None
                updated_df.at[idx, "Sport Key"] = None
                updated_df.at[idx, "Commence Time"] = None

    return updated_df[INPUT_COLUMNS].copy()


def build_matchup_cards(display_df: pd.DataFrame) -> list[dict[str, object]]:
    """Convert shared board rows into compact card payloads for Reflex."""
    cards = []
    for _, row in display_df.iterrows():
        away_team = row["Away"]
        home_team = row["Home"]
        away_brand = get_team_branding(away_team)
        home_brand = get_team_branding(home_team)
        cards.append(
            {
                "matchup": f"{away_team} at {home_team}",
                "matchup_label": format_matchup_label(away_team, home_team),
                "away_team": away_team,
                "home_team": home_team,
                "away_pitcher": row["Away Pitcher"],
                "home_pitcher": row["Home Pitcher"],
                "away_win": row["Away Win"],
                "home_win": row["Home Win"],
                "probability_line": format_matchup_probability_line(
                    away_team,
                    row["Away Win"],
                    home_team,
                    row["Home Win"],
                ),
                "away_logo": get_team_logo_src(away_team),
                "home_logo": get_team_logo_src(home_team),
                "away_abbr": away_brand["abbr"],
                "home_abbr": home_brand["abbr"],
                "away_primary": away_brand["primary"],
                "home_primary": home_brand["primary"],
                "projected_score": f"{row['Away Runs']:.2f} - {row['Home Runs']:.2f}",
                "projected_total": row["Projected Total"],
                "best_bet": row["Best Bet"],
                "bet_flag": row["Bet Flag"],
                "signal_label": format_signal_label(str(row["Bet Flag"])),
                "best_total_bet": row["Best Total Bet"],
                "total_bet_flag": row["Total Bet Flag"],
                "side_summary": f"{row['Best Bet']} | {row['Bet Flag']}" if row["Best Bet"] != "Pass" else "No side bet",
                "market_summary": "Market unavailable"
                if pd.isna(row["Away Moneyline"]) or pd.isna(row["Home Moneyline"])
                else f"Away {format_moneyline(row['Away Moneyline'])} / Home {format_moneyline(row['Home Moneyline'])}",
                "market_available": "false"
                if pd.isna(row["Away Moneyline"]) or pd.isna(row["Home Moneyline"])
                else "true",
                "away_market_ml": ""
                if pd.isna(row["Away Moneyline"])
                else format_moneyline(row["Away Moneyline"]),
                "home_market_ml": ""
                if pd.isna(row["Home Moneyline"])
                else format_moneyline(row["Home Moneyline"]),
                "away_fair_ml": format_moneyline(row["Away Fair ML"]),
                "home_fair_ml": format_moneyline(row["Home Fair ML"]),
                "away_ev": "" if pd.isna(row["Away EV"]) else f"{float(row['Away EV']):.2f}",
                "home_ev": "" if pd.isna(row["Home EV"]) else f"{float(row['Home EV']):.2f}",
                "away_edge_pct": "" if pd.isna(row["Away Edge %"]) else f"{float(row['Away Edge %']):.2f}",
                "home_edge_pct": "" if pd.isna(row["Home Edge %"]) else f"{float(row['Home Edge %']):.2f}",
                "favorite": row["Favorite"],
                "win_edge": row["Win Edge"],
                "away_runs_proj": f"{float(row['Away Runs']):.2f}",
                "home_runs_proj": f"{float(row['Home Runs']):.2f}",
                "sportsbook": "" if pd.isna(row["Sportsbook"]) else str(row["Sportsbook"]),
            }
        )
    return cards


def build_summary_card_records(display_df: pd.DataFrame) -> list[dict[str, str]]:
    """Translate shared summary metrics into Reflex KPI card rows."""
    metrics = build_summary_metrics(display_df)
    return [
        {"label": "Games", "value": str(metrics["games_today"]), "delta": "Today's loaded board"},
        {"label": "Avg Total", "value": str(metrics["avg_total_runs"]), "delta": "Projected combined runs"},
        {"label": "Best EV", "value": str(metrics["strongest_ev"]), "delta": str(metrics["strongest_ev_delta"] or "No positive edge yet")},
        {"label": "Playable Bets", "value": str(metrics["playable_bets"]), "delta": f"{metrics['playable_total_bets']} totals flagged"},
    ]


def build_top_plays(display_df: pd.DataFrame, max_plays: int = 6) -> list[dict[str, object]]:
    """Return top plays as plain records for Reflex cards/tables."""
    top_plays_df = build_top_plays_dataframe(display_df, max_plays=max_plays)
    if top_plays_df.empty:
        return []
    records = top_plays_df.to_dict("records")
    for record in records:
        if record.get("ev") is not None:
            record["ev"] = f"{float(record['ev']):.1f}%"
        if record.get("model_edge") is not None:
            record["edge"] = f"{float(record['model_edge']):+.1f}%"
        else:
            record["edge"] = "N/A"
        record["line"] = str(record.get("line", "N/A"))
    return records


def build_shared_display_dataframe(
    inputs: dict[str, pd.DataFrame],
    daily_board_inputs: pd.DataFrame | None = None,
    live_odds_market_data: dict[tuple[str, str], dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Build the shared board dataframe for Reflex using live market data."""
    market_lookup = live_odds_market_data or load_board_market_context(inputs)[0]
    if daily_board_inputs is None:
        daily_board_inputs = build_reflex_daily_input_table(inputs, market_lookup)

    display_df = build_display_dataframe(
        daily_board_inputs=daily_board_inputs,
        pitcher_ratings=inputs["pitcher_ratings"],
        team_ratings=inputs["team_ratings"],
        normalize_team_name_fn=normalize_team_name,
        live_odds_market_data=market_lookup,
    )
    display_df = display_df.copy()
    display_df["Event Id"] = ""
    display_df["Bookmaker Key"] = ""
    display_df["Sport Key"] = ""
    display_df["Commence Time"] = ""
    for idx, row in display_df.iterrows():
        market_row = market_lookup.get(
            (
                normalize_team_name(str(row["Away"])),
                normalize_team_name(str(row["Home"])),
            ),
            {},
        )
        display_df.at[idx, "Event Id"] = "" if market_row.get("event_id") is None else str(market_row.get("event_id"))
        display_df.at[idx, "Bookmaker Key"] = "" if market_row.get("bookmaker_key") is None else str(market_row.get("bookmaker_key"))
        display_df.at[idx, "Sport Key"] = "" if market_row.get("sport_key") is None else str(market_row.get("sport_key"))
        display_df.at[idx, "Commence Time"] = "" if market_row.get("commence_time") is None else str(market_row.get("commence_time"))

    extra_columns = ["Event Id", "Bookmaker Key", "Sport Key", "Commence Time"]
    return display_df[[*TABLE_COLUMNS, *extra_columns]].copy()


def read_prediction_rows(limit: int = 10) -> list[dict[str, object]]:
    """Read saved prediction rows for the projections page."""
    query = """
        SELECT
            p.game_id,
            g.game_date,
            away.team_name AS away_team,
            home.team_name AS home_team,
            p.home_win_prob,
            p.away_win_prob,
            p.market_home_implied_prob_no_vig,
            p.market_away_implied_prob_no_vig,
            p.edge_home,
            p.edge_away,
            p.recommended_side
        FROM predictions p
        JOIN games g ON g.game_id = p.game_id
        JOIN teams away ON away.team_id = g.away_team_id
        JOIN teams home ON home.team_id = g.home_team_id
        ORDER BY p.prediction_time DESC
        LIMIT ?
    """
    if not DB_PATH.exists():
        return []
    try:
        with get_connection() as connection:
            rows = pd.read_sql_query(query, connection, params=[limit])
    except sqlite3.Error:
        return []
    return rows.to_dict("records")
