"""Aggregate project data for the Reflex UI."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import sqlite3

from app.utils.season_monitor import (
    build_bullpen_monitor,
    build_current_division_standings,
    build_lineup_monitor,
    build_model_movers,
    build_pitcher_watch,
    build_projected_standings,
    build_today_impact,
    simulate_playoff_odds,
)
from model.weather_api import get_weather_for_team
from project_config import DB_PATH, DEFAULT_RUN_DISPERSION, DEFAULT_SIMS, MODEL_DIR

from .legacy_adapter import (
    build_matchup_cards,
    load_board_market_context,
    build_reflex_daily_input_table,
    build_shared_display_dataframe,
    build_summary_card_records,
    build_top_plays,
    clear_caches,
    get_selected_slate_date,
    load_core_inputs,
    read_prediction_rows,
    read_upcoming_prediction_rows,
)
from .performance_tracker import (
    build_performance_summary,
    delete_performance_rows,
    grade_performance_bets,
    load_performance_rows,
    save_snapshot_records,
)


def _table_records(dataframe, limit: int | None = None) -> list[dict[str, object]]:
    if dataframe is None or dataframe.empty:
        return []
    if limit is not None:
        dataframe = dataframe.head(limit).copy()
    return dataframe.to_dict("records")


def _stringify_records(records: list[dict[str, object]]) -> list[dict[str, str]]:
    clean_rows: list[dict[str, str]] = []
    for row in records:
        clean_rows.append(
            {
                str(key): "" if value is None else str(value)
                for key, value in row.items()
            }
        )
    return clean_rows


def build_performance_payload() -> dict[str, object]:
    performance_rows = load_performance_rows()
    performance_summary = build_performance_summary()
    return {
        "summary_cards": _stringify_records(performance_summary),
        "rows": _stringify_records(performance_rows),
        "columns": [
            "Snapshot",
            "Date",
            "Matchup",
            "Bet Type",
            "Pick",
            "Locked Odds",
            "Model Edge",
            "EV",
            "Result",
            "Units",
        ],
    }


def _format_refresh_timestamp(value: object) -> str:
    if value in (None, ""):
        return "Not refreshed yet"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return parsed.astimezone().strftime("%b %d, %I:%M %p")


def _read_table_count(connection: sqlite3.Connection, table_name: str) -> int:
    """Return a simple row count for one SQLite table."""
    return int(connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def build_data_health_rows(inputs: dict[str, object]) -> list[dict[str, str]]:
    """Build a compact data health summary for the Settings page."""
    counts = {
        "games": 0,
        "teams": 0,
        "starting_pitchers": 0,
        "team_daily_stats": 0,
        "pitcher_daily_stats": 0,
        "model_features": 0,
        "predictions": 0,
    }
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as connection:
            for table_name in counts:
                counts[table_name] = _read_table_count(connection, table_name)

    weather_team = ""
    weather_source = "Unavailable"
    weather_temp = "-"
    matchups = inputs.get("matchups")
    stadium_locations = inputs.get("stadium_locations")
    if matchups is not None and stadium_locations is not None and not matchups.empty:
        weather_team = str(matchups.iloc[0].get("home_team", "")).strip()
        if weather_team:
            weather_snapshot = get_weather_for_team(
                home_team=weather_team,
                stadium_df=stadium_locations,
                data_mode="live",
            )
            weather_source = str(weather_snapshot.get("weather_source", "Unavailable"))
            temperature_value = weather_snapshot.get("temperature_f")
            weather_temp = "-" if temperature_value in (None, "") else str(temperature_value)

    stats_ready = counts["team_daily_stats"] > 0 or counts["pitcher_daily_stats"] > 0
    features_ready = counts["model_features"] > 0
    predictions_ready = counts["predictions"] > 0

    return [
        {"Item": "Games Loaded", "Value": str(counts["games"])},
        {"Item": "Teams Loaded", "Value": str(counts["teams"])},
        {"Item": "Starting Pitchers Loaded", "Value": str(counts["starting_pitchers"])},
        {"Item": "Team Stats Rows", "Value": str(counts["team_daily_stats"])},
        {"Item": "Pitcher Stats Rows", "Value": str(counts["pitcher_daily_stats"])},
        {"Item": "Feature Rows", "Value": str(counts["model_features"])},
        {"Item": "Prediction Rows", "Value": str(counts["predictions"])},
        {"Item": "MLB Stats Status", "Value": "Loaded" if stats_ready else "Missing"},
        {"Item": "Feature Pipeline Status", "Value": "Ready" if features_ready else "Waiting"},
        {"Item": "Prediction Pipeline Status", "Value": "Ready" if predictions_ready else "Waiting"},
        {"Item": "Weather Probe Team", "Value": weather_team or "No slate loaded"},
        {"Item": "Weather Probe Source", "Value": weather_source},
        {"Item": "Weather Probe Temp", "Value": weather_temp},
    ]


@lru_cache(maxsize=2)
def build_app_payload(force_live_odds: bool = False) -> dict[str, object]:
    inputs = load_core_inputs()
    slate_date = get_selected_slate_date(inputs["matchups"])
    live_odds_market_data, odds_status = load_board_market_context(
        inputs,
        force_refresh=force_live_odds,
    )
    daily_board_inputs = build_reflex_daily_input_table(inputs, live_odds_market_data)
    display_df = build_shared_display_dataframe(inputs, daily_board_inputs, live_odds_market_data)
    top_plays = build_top_plays(display_df)
    matchup_cards = build_matchup_cards(display_df)
    summary_cards = build_summary_card_records(display_df)

    pitcher_watch_df, today_pitchers_df = build_pitcher_watch(inputs["pitcher_ratings"], daily_board_inputs)
    lineup_df = build_lineup_monitor(inputs["team_ratings"], inputs["hitter_ratings"], inputs["projected_lineups"])
    bullpen_leaders_df, bullpen_stress_df = build_bullpen_monitor(inputs["team_ratings"])
    movers_df = build_model_movers(inputs["team_ratings"])
    today_impact_cards = build_today_impact(daily_board_inputs, bullpen_stress_df)
    projected_df = build_projected_standings(inputs["team_ratings"])
    current_standings_df = build_current_division_standings(inputs["team_ratings"])
    playoff_odds_df = simulate_playoff_odds(inputs["team_ratings"])
    prediction_rows = read_prediction_rows(limit=12)
    upcoming_prediction_rows = read_upcoming_prediction_rows(limit=20)
    performance_payload = build_performance_payload()
    data_health_rows = build_data_health_rows(inputs)

    return {
        "summary_cards": _stringify_records(summary_cards),
        "top_plays": _stringify_records(top_plays),
        "matchup_cards": _stringify_records(matchup_cards),
        "matchup_rows": _stringify_records(_table_records(display_df)),
        "matchup_columns": list(display_df.columns),
        "driver_tables": {
            "today_pitchers": _stringify_records(_table_records(today_pitchers_df, limit=10)),
            "pitcher_watch": _stringify_records(_table_records(pitcher_watch_df, limit=12)),
            "lineups": _stringify_records(_table_records(lineup_df, limit=12)),
            "bullpen_leaders": _stringify_records(_table_records(bullpen_leaders_df, limit=12)),
            "bullpen_stress": _stringify_records(_table_records(bullpen_stress_df, limit=12)),
            "model_movers": _stringify_records(_table_records(movers_df, limit=12)),
        },
        "today_impact_cards": _stringify_records(today_impact_cards),
        "projection_tables": {
            "projected": _stringify_records(_table_records(projected_df)),
            "current": _stringify_records(_table_records(current_standings_df)),
            "playoff": _stringify_records(_table_records(playoff_odds_df)),
            "predictions": _stringify_records(prediction_rows),
            "upcoming_predictions": _stringify_records(upcoming_prediction_rows),
        },
        "settings_tables": {
            "runtime": [
                {"Item": "Database Path", "Value": str(DB_PATH)},
                {"Item": "Database Exists", "Value": str(DB_PATH.exists())},
                {"Item": "Default Sims", "Value": str(DEFAULT_SIMS)},
                {"Item": "Run Dispersion", "Value": str(DEFAULT_RUN_DISPERSION)},
                {"Item": "Model Directory", "Value": str(MODEL_DIR)},
                {"Item": "Odds Source", "Value": str(odds_status.get("source", "CACHE"))},
                {"Item": "Odds Last Refresh", "Value": _format_refresh_timestamp(odds_status.get("last_refreshed_at"))},
                {"Item": "Odds Auto Refresh", "Value": "Enabled" if odds_status.get("auto_refresh_enabled", True) else "Manual only"},
            ],
            "data_health": data_health_rows,
            "streamlit_entrypoints": [
                {"Category": "Streamlit Entrypoint", "Path": "app/app.py"},
                {"Category": "Streamlit Entrypoint", "Path": "launch_streamlit.bat"},
            ],
            "reused_modules": [
                {"Category": "Reused Module", "Path": "model/game_engine.py"},
                {"Category": "Reused Module", "Path": "model/simulate_games.py"},
                {"Category": "Reused Module", "Path": "model/schedule_loader.py"},
                {"Category": "Reused Module", "Path": "model/team_loader.py"},
                {"Category": "Reused Module", "Path": "model/lineup_strength.py"},
                {"Category": "Shared Service", "Path": "app/services/board_data.py"},
                {"Category": "Reused Module", "Path": "app/utils/season_monitor.py"},
                {"Category": "Reused Module", "Path": "app/utils/probabilities.py"},
                {"Category": "Reused Module", "Path": "app/db/connection.py"},
            ],
        },
        "audit": {
            "streamlit_entrypoints": ["app/app.py", "launch_streamlit.bat"],
            "model_modules": [
                "model/game_engine.py",
                "model/simulate_games.py",
                "model/schedule_loader.py",
                "model/team_loader.py",
                "model/lineup_strength.py",
                "app/services/board_data.py",
                "app/utils/season_monitor.py",
                "app/utils/probabilities.py",
                "app/db/connection.py",
            ],
            "db_path": str(DB_PATH),
            "db_exists": str(DB_PATH.exists()),
            "default_sims": str(DEFAULT_SIMS),
            "default_run_dispersion": str(DEFAULT_RUN_DISPERSION),
            "model_dir": str(MODEL_DIR),
        },
        "filters": {
            "teams": ["All Teams"] + sorted(set(display_df["Home"].dropna().unique().tolist() + display_df["Away"].dropna().unique().tolist())),
            "signals": ["All Signals", "Strong Bet", "Lean", "Pass"],
        },
        "performance": performance_payload,
        "odds_status": {
            "source": str(odds_status.get("source", "CACHE")),
            "last_refreshed_at": _format_refresh_timestamp(odds_status.get("last_refreshed_at")),
            "requests_remaining": "" if odds_status.get("requests_remaining") is None else str(odds_status.get("requests_remaining")),
            "requests_used": "" if odds_status.get("requests_used") is None else str(odds_status.get("requests_used")),
            "credits_last": "" if odds_status.get("credits_last") is None else str(odds_status.get("credits_last")),
            "auto_refresh_enabled": "true" if odds_status.get("auto_refresh_enabled", True) else "false",
            "manual_only": "true" if odds_status.get("manual_only", False) else "false",
            "slate_date": slate_date or "",
            "error_message": "" if not odds_status.get("error_message") else str(odds_status.get("error_message")),
        },
    }


def refresh_app_payload(force_live_odds: bool = True) -> dict[str, object]:
    clear_caches()
    build_app_payload.cache_clear()
    return build_app_payload(force_live_odds=force_live_odds)


def lock_performance_snapshot(
    board_rows: list[dict[str, str]],
    game_date: str | None,
    tracking_mode: str = "full_visible_board",
    snapshot_note: str | None = None,
) -> dict[str, object]:
    snapshot_results = save_snapshot_records(
        board_rows,
        game_date,
        tracking_mode=tracking_mode,
        snapshot_note=snapshot_note,
    )
    performance_payload = build_performance_payload()
    return {
        **snapshot_results,
        "performance": performance_payload,
    }


def grade_performance_snapshot_results() -> dict[str, object]:
    grading_results = grade_performance_bets()
    performance_payload = build_performance_payload()
    return {
        "grading_results": grading_results,
        "performance": performance_payload,
    }
def delete_tracked_performance_rows(performance_bet_ids: list[int]) -> dict[str, object]:
    deleted_rows = delete_performance_rows(performance_bet_ids)
    performance_payload = build_performance_payload()
    return {
        "deleted_rows": deleted_rows,
        "performance": performance_payload,
    }
