"""Reflex state for loading and filtering the sportsbook UI."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import pandas as pd
import reflex as rx

from reflex_app.services.app_data import (
    build_app_payload,
    build_performance_payload,
    delete_tracked_performance_rows,
    grade_performance_snapshot_results,
    lock_performance_snapshot,
    refresh_app_payload,
)
from reflex_app.services.live_odds import get_matchup_totals_detail
from reflex_app.services.ui_formatters import (
    coerce_probability,
    format_matchup_label,
    format_matchup_probability_line,
    short_team_name,
)


def _initial_payload() -> dict[str, object]:
    """Best-effort initial UI payload so first render is not blocked on mount."""
    try:
        return build_app_payload()
    except Exception:
        return {
            "summary_cards": [],
            "top_plays": [],
            "matchup_cards": [],
            "matchup_rows": [],
            "matchup_columns": [],
            "today_impact_cards": [],
            "driver_tables": {
                "today_pitchers": [],
                "pitcher_watch": [],
                "lineups": [],
                "bullpen_leaders": [],
                "bullpen_stress": [],
                "model_movers": [],
            },
            "projection_tables": {
                "projected": [],
                "current": [],
                "playoff": [],
                "predictions": [],
                "upcoming_predictions": [],
            },
            "settings_tables": {
                "runtime": [],
                "data_health": [],
                "streamlit_entrypoints": [],
                "reused_modules": [],
            },
            "performance": {
                "summary_cards": [],
                "rows": [],
                "columns": [],
            },
            "filters": {
                "teams": ["All Teams"],
                "signals": ["All Signals", "Strong Bet", "Lean", "Pass"],
            },
            "odds_status": {
                "source": "CACHE",
                "last_refreshed_at": "Not refreshed yet",
                "requests_remaining": "",
                "requests_used": "",
                "credits_last": "",
                "auto_refresh_enabled": "true",
                "manual_only": "false",
                "slate_date": "",
                "error_message": "",
            },
        }


INITIAL_PAYLOAD = _initial_payload()
TEST_HIGHLIGHT_MODE = True


def _short_driver_label(label: str) -> str:
    """Collapse verbose driver labels into scan-friendly card copy."""
    label_map = {
        "Biggest Starter Edge": "Starter Advantage",
        "Biggest Lineup Boost": "Lineup Edge",
        "Biggest Bullpen Risk": "Bullpen Signal",
        "Best Unit Mismatch": "Unit Mismatch",
    }
    return label_map.get(label, label)


def _format_driver_line(item: dict[str, str], matchup: str) -> str:
    """Format a compact driver bullet for the Dashboard Top Leans cards."""
    label = _short_driver_label(str(item.get("label", "")).strip())
    team = str(item.get("team", "")).strip()
    raw_value = str(item.get("value", "")).strip()
    value = raw_value.replace(f" | {matchup}", "").replace(f"{matchup} | ", "").strip()
    if not value:
        return f"{label}: {team}" if team else label
    if team:
        return f"{label}: {team} ({value})"
    return f"{label}: {value}"


def _confidence_label(win_edge: str) -> str:
    """Map edge strength into a simple confidence label for Dashboard UI."""
    try:
        edge_value = abs(float(win_edge or 0))
    except (TypeError, ValueError):
        edge_value = 0.0
    if edge_value >= 20:
        return "Strong"
    if edge_value >= 10:
        return "Lean"
    return "Weak"


def _round_number_in_text(text: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        try:
            value = float(match.group(0))
        except ValueError:
            return match.group(0)
        prefix = "+" if match.group(0).startswith("+") and value >= 0 else ""
        return f"{prefix}{value:.2f}"

    return re.sub(r"[+-]?\d+(?:\.\d+)?", replacer, str(text))


def _build_driver_note(label: str, value: str, team: str) -> str:
    if label == "Strongest Starter Edge":
        return "Clear SP advantage"
    if label == "Biggest Lineup Edge":
        return "Elite offensive boost"
    if label == "Highest Bullpen Risk":
        if "At Risk" in value or "Stressed" in value:
            return "Potential late risk"
        return "Bullpen volatility rising"
    if label == "Best Team Profile":
        return f"{short_team_name(team)} rates as the strongest unit"
    return "Top board signal"


def _format_two_decimals(value: str | float | int | None) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(str(value).replace('%', '').strip()):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _pitcher_tier(rank_value: str | int) -> str:
    try:
        rank_number = int(float(rank_value))
    except (TypeError, ValueError):
        return "Solid"
    if rank_number == 1:
        return "Elite"
    if rank_number <= 3:
        return "Strong"
    return "Solid"


def _bullpen_status_label(status: str) -> str:
    status_map = {
        "Fresh": "Fresh",
        "Stable": "Stable",
        "Watch": "Elevated",
        "Stressed": "At Risk",
    }
    return status_map.get(str(status), str(status) or "-")


def _volatility_label(value: str | float | int | None) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "Medium"
    if numeric_value <= 0.03:
        return "Low"
    if numeric_value <= 0.08:
        return "Medium"
    return "High"


def _probability_gap(card: dict[str, str]) -> float:
    away_win = _to_float(card.get("away_win")) or 0.0
    home_win = _to_float(card.get("home_win")) or 0.0
    return abs(away_win - home_win)


def _team_profile_descriptor(row: dict[str, str]) -> str:
    power = _to_float(row.get("Power Score")) or 0.0
    offense = _to_float(row.get("Offense Score")) or 0.0
    pitching = _to_float(row.get("Pitching Score")) or 0.0
    bullpen = _to_float(row.get("Bullpen Score")) or 0.0
    metrics = {
        "Offense": offense,
        "Pitching": pitching,
        "Bullpen": bullpen,
    }
    spread = max(metrics.values()) - min(metrics.values())
    if spread <= 0.04:
        return "Balanced"
    top_unit = max(metrics, key=metrics.get)
    if power >= 1.08:
        return f"{top_unit}-driven"
    return "Elite"


def _to_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _tracking_mode_label(value: str) -> str:
    label_map = {
        "full_visible_board": "Full Visible Board",
        "model_leans_only": "Model Leans Only",
        "actionable_only": "Actionable Only",
    }
    return label_map.get(str(value).strip(), "Full Visible Board")


def _tracking_mode_value(label: str) -> str:
    value_map = {
        "Full Visible Board": "full_visible_board",
        "Model Leans Only": "model_leans_only",
        "Actionable Only": "actionable_only",
    }
    return value_map.get(str(label).strip(), "full_visible_board")


def _safe_float(value: str | float | int | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _to_moneyline_int(value: str | float | int | None) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _edge_cents(fair_price: str | int | None, market_price: str | int | None) -> int | None:
    fair_line = _to_moneyline_int(fair_price)
    market_line = _to_moneyline_int(market_price)
    if fair_line is None or market_line is None:
        return None
    if fair_line < 0:
        return abs(fair_line) - abs(market_line)
    return abs(market_line) - abs(fair_line)


def _daily_status_label(card: dict[str, str]) -> str:
    if str(card.get("market_available", "")).lower() != "true":
        return "Waiting"
    signal = str(card.get("signal_label", "")).strip()
    return signal or "Pass"


def _ev_status_label(card: dict[str, str], lean_is_away: bool) -> str:
    if str(card.get("market_available", "")).lower() != "true":
        return "Waiting for market"
    ev_value = _to_float(card.get("away_ev" if lean_is_away else "home_ev"))
    if ev_value is not None and ev_value > 0:
        return "Positive EV"
    return "No Edge"


def _driver_tag_label(item: dict[str, str], away_team: str, home_team: str) -> str | None:
    team = str(item.get("team", "")).strip()
    if team not in {away_team, home_team}:
        return None
    label = str(item.get("headline") or item.get("label") or "").strip()
    label_map = {
        "Strongest Starter Edge": "Starter Edge",
        "Biggest Lineup Edge": "Lineup Edge",
        "Highest Bullpen Risk": "Bullpen Risk",
        "Best Team Profile": "Team Profile",
    }
    return f"{label_map.get(label, label)}: {short_team_name(team)}"


class AppState(rx.State):
    """Shared UI state for all Reflex pages."""

    state_auto_setters = False

    is_loading: bool = False
    selected_team: str = "All Teams"
    selected_signal: str = "All Signals"
    selected_performance_market: str = "All"
    selected_performance_edge_bucket: str = "All Buckets"
    selected_performance_date_range: str = "All Dates"
    performance_best_bet_only: str = "All Bets"
    selected_performance_actionability: str = "All Rows"
    selected_performance_tracking_mode: str = "All Modes"
    selected_snapshot_tracking_mode: str = "Full Visible Board"
    snapshot_note_input: str = ""
    show_full_matchup_table: bool = False
    odds_status_collapsed: bool = True
    performance_notice: str = ""
    summary_cards: list[dict[str, str]] = INITIAL_PAYLOAD["summary_cards"]
    top_plays: list[dict[str, str]] = INITIAL_PAYLOAD["top_plays"]
    matchup_cards: list[dict[str, str]] = INITIAL_PAYLOAD["matchup_cards"]
    matchup_rows: list[dict[str, str]] = INITIAL_PAYLOAD["matchup_rows"]
    matchup_columns: list[str] = INITIAL_PAYLOAD["matchup_columns"]
    today_impact_cards: list[dict[str, str]] = INITIAL_PAYLOAD["today_impact_cards"]
    team_options: list[str] = INITIAL_PAYLOAD["filters"]["teams"]
    signal_options: list[str] = INITIAL_PAYLOAD["filters"]["signals"]
    driver_today_pitchers: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["today_pitchers"]
    driver_pitcher_watch: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["pitcher_watch"]
    driver_lineups: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["lineups"]
    driver_bullpen_leaders: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["bullpen_leaders"]
    driver_bullpen_stress: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["bullpen_stress"]
    driver_model_movers: list[dict[str, str]] = INITIAL_PAYLOAD["driver_tables"]["model_movers"]
    projected_rows: list[dict[str, str]] = INITIAL_PAYLOAD["projection_tables"]["projected"]
    current_rows: list[dict[str, str]] = INITIAL_PAYLOAD["projection_tables"]["current"]
    playoff_rows: list[dict[str, str]] = INITIAL_PAYLOAD["projection_tables"]["playoff"]
    prediction_rows: list[dict[str, str]] = INITIAL_PAYLOAD["projection_tables"]["predictions"]
    upcoming_prediction_rows: list[dict[str, str]] = INITIAL_PAYLOAD["projection_tables"]["upcoming_predictions"]
    performance_summary_cards: list[dict[str, str]] = INITIAL_PAYLOAD["performance"]["summary_cards"]
    performance_rows: list[dict[str, str]] = INITIAL_PAYLOAD["performance"]["rows"]
    performance_columns: list[str] = INITIAL_PAYLOAD["performance"]["columns"]
    runtime_rows: list[dict[str, str]] = INITIAL_PAYLOAD["settings_tables"]["runtime"]
    data_health_rows: list[dict[str, str]] = INITIAL_PAYLOAD["settings_tables"]["data_health"]
    streamlit_entrypoint_rows: list[dict[str, str]] = INITIAL_PAYLOAD["settings_tables"]["streamlit_entrypoints"]
    reused_module_rows: list[dict[str, str]] = INITIAL_PAYLOAD["settings_tables"]["reused_modules"]
    odds_status: dict[str, str] = INITIAL_PAYLOAD["odds_status"]
    expanded_matchup_key: str = ""
    matchup_totals_details: dict[str, dict[str, str]] = {}

    def _apply_payload(self, payload: dict[str, object]) -> None:
        self.summary_cards = payload["summary_cards"]
        self.top_plays = payload["top_plays"]
        self.matchup_cards = payload["matchup_cards"]
        self.matchup_rows = payload["matchup_rows"]
        self.matchup_columns = payload["matchup_columns"]
        self.today_impact_cards = payload["today_impact_cards"]
        self.team_options = payload["filters"]["teams"]
        self.signal_options = payload["filters"]["signals"]
        self.driver_today_pitchers = payload["driver_tables"]["today_pitchers"]
        self.driver_pitcher_watch = payload["driver_tables"]["pitcher_watch"]
        self.driver_lineups = payload["driver_tables"]["lineups"]
        self.driver_bullpen_leaders = payload["driver_tables"]["bullpen_leaders"]
        self.driver_bullpen_stress = payload["driver_tables"]["bullpen_stress"]
        self.driver_model_movers = payload["driver_tables"]["model_movers"]
        self.projected_rows = payload["projection_tables"]["projected"]
        self.current_rows = payload["projection_tables"]["current"]
        self.playoff_rows = payload["projection_tables"]["playoff"]
        self.prediction_rows = payload["projection_tables"]["predictions"]
        self.upcoming_prediction_rows = payload["projection_tables"]["upcoming_predictions"]
        self.performance_summary_cards = payload["performance"]["summary_cards"]
        self.performance_rows = payload["performance"]["rows"]
        self.performance_columns = payload["performance"]["columns"]
        self.runtime_rows = payload["settings_tables"]["runtime"]
        self.data_health_rows = payload["settings_tables"]["data_health"]
        self.streamlit_entrypoint_rows = payload["settings_tables"]["streamlit_entrypoints"]
        self.reused_module_rows = payload["settings_tables"]["reused_modules"]
        self.odds_status = payload["odds_status"]

    def load(self) -> None:
        if self.summary_cards and self.matchup_cards:
            self.is_loading = False
            return
        self.is_loading = True
        try:
            self._apply_payload(build_app_payload())
        except Exception as exc:
            print(f"[Reflex App] Initial load failed: {exc}")
        self.is_loading = False

    def refresh(self) -> None:
        self.is_loading = True
        try:
            self._apply_payload(refresh_app_payload(force_live_odds=True))
        except Exception as exc:
            print(f"[Reflex App] Refresh failed: {exc}")
        self.is_loading = False

    def _apply_performance_payload(self, payload: dict[str, object]) -> None:
        self.performance_summary_cards = payload["summary_cards"]
        self.performance_rows = payload["rows"]
        self.performance_columns = payload["columns"]

    def set_selected_team(self, value: str) -> None:
        self.selected_team = value

    def set_selected_signal(self, value: str) -> None:
        self.selected_signal = value

    def set_selected_performance_market(self, value: str) -> None:
        self.selected_performance_market = value

    def set_selected_performance_edge_bucket(self, value: str) -> None:
        self.selected_performance_edge_bucket = value

    def set_selected_performance_date_range(self, value: str) -> None:
        self.selected_performance_date_range = value

    def set_performance_best_bet_only(self, value: str) -> None:
        self.performance_best_bet_only = value

    def set_selected_performance_actionability(self, value: str) -> None:
        self.selected_performance_actionability = value

    def set_selected_performance_tracking_mode(self, value: str) -> None:
        self.selected_performance_tracking_mode = value

    def set_selected_snapshot_tracking_mode(self, value: str) -> None:
        self.selected_snapshot_tracking_mode = value

    def set_snapshot_note_input(self, value: str) -> None:
        self.snapshot_note_input = value

    def set_show_full_matchup_table(self, value: bool) -> None:
        self.show_full_matchup_table = value

    def toggle_show_full_matchup_table(self) -> None:
        self.show_full_matchup_table = not self.show_full_matchup_table

    def toggle_odds_status_collapsed(self) -> None:
        self.odds_status_collapsed = not self.odds_status_collapsed

    def lock_snapshot(self) -> None:
        visible_rows = list(self.filtered_matchups)
        if not visible_rows:
            self.performance_notice = "No visible games are currently on the board. Reset filters or refresh the slate, then save again."
            return

        game_date = str(self.odds_status.get("slate_date", "")).strip() or None
        tracking_mode = _tracking_mode_value(self.selected_snapshot_tracking_mode)
        try:
            results = lock_performance_snapshot(
                visible_rows,
                game_date,
                tracking_mode=tracking_mode,
                snapshot_note=self.snapshot_note_input,
            )
        except Exception as exc:
            print(f"[Reflex Performance] Snapshot save failed: {exc}")
            self.performance_notice = "Board snapshot could not be saved right now. Check the database connection and deployment logs."
            return
        self._apply_performance_payload(results["performance"])
        saved_rows = int(results.get("saved_rows", 0))
        actionable_rows = int(results.get("actionable_rows", 0))
        non_actionable_rows = int(results.get("non_actionable_rows", 0))
        tracking_mode_label = _tracking_mode_label(str(results.get("tracking_mode", tracking_mode)))
        if saved_rows == 0:
            if tracking_mode == "actionable_only":
                self.performance_notice = "No actionable bets are currently flagged on the visible board. Switch to Full Visible Board or Model Leans Only to paper-track this slate."
            else:
                self.performance_notice = "No visible games could be saved from the current board view."
            return
        if actionable_rows == 0:
            self.snapshot_note_input = ""
            self.performance_notice = (
                f"No actionable bets are currently flagged. Saved {saved_rows} visible model row(s) instead via {tracking_mode_label}."
            )
            return
        if non_actionable_rows > 0:
            self.snapshot_note_input = ""
            self.performance_notice = (
                f"Saved {saved_rows} board snapshot row(s) via {tracking_mode_label}, including {actionable_rows} actionable and {non_actionable_rows} non-actionable model rows."
            )
            return
        self.snapshot_note_input = ""
        self.performance_notice = f"Saved {saved_rows} actionable snapshot row(s) via {tracking_mode_label}."

    def grade_performance_results(self) -> None:
        try:
            results = grade_performance_snapshot_results()
        except Exception as exc:
            print(f"[Reflex Performance] Grading failed: {exc}")
            self.performance_notice = "Results could not be graded right now. Final scores or database writes may be unavailable."
            return
        self._apply_performance_payload(results["performance"])
        grading_results = results.get("grading_results", {})
        graded_rows = int(grading_results.get("graded_rows", 0))
        eligible_rows = int(grading_results.get("eligible_rows", 0))
        self.performance_notice = (
            f"Graded {graded_rows} of {eligible_rows} eligible paper bet row(s)."
            if eligible_rows > 0
            else "No saved paper bets were ready for grading yet."
        )

    def delete_filtered_performance_rows(self) -> None:
        visible_rows = list(self.filtered_performance_rows)
        if not visible_rows:
            self.performance_notice = "No tracked rows match the current filters, so there was nothing to delete."
            return

        performance_bet_ids: list[int] = []
        for row in visible_rows:
            raw_id = str(row.get("_performance_bet_id", "")).strip()
            if not raw_id:
                continue
            try:
                performance_bet_ids.append(int(raw_id))
            except ValueError:
                continue

        if not performance_bet_ids:
            self.performance_notice = "The filtered rows could not be resolved for deletion."
            return

        try:
            results = delete_tracked_performance_rows(performance_bet_ids)
        except Exception as exc:
            print(f"[Reflex Performance] Delete failed: {exc}")
            self.performance_notice = "Tracked rows could not be deleted right now. Check deployment logs for details."
            return
        self._apply_performance_payload(results["performance"])
        deleted_rows = int(results.get("deleted_rows", 0))
        if deleted_rows > 0:
            self.performance_notice = f"Deleted {deleted_rows} tracked row(s) from the current Performance view."
            return
        self.performance_notice = "No tracked rows were deleted."

    def delete_performance_row(self, performance_bet_id: str) -> None:
        raw_id = str(performance_bet_id).strip()
        if not raw_id:
            self.performance_notice = "That tracked row could not be resolved for deletion."
            return

        try:
            target_id = int(raw_id)
        except ValueError:
            self.performance_notice = "That tracked row could not be resolved for deletion."
            return

        try:
            results = delete_tracked_performance_rows([target_id])
        except Exception as exc:
            print(f"[Reflex Performance] Row delete failed: {exc}")
            self.performance_notice = "That tracked row could not be deleted right now."
            return
        self._apply_performance_payload(results["performance"])
        deleted_rows = int(results.get("deleted_rows", 0))
        if deleted_rows > 0:
            self.performance_notice = "Deleted 1 tracked row from Performance."
            return
        self.performance_notice = "That tracked row was not deleted."

    def toggle_matchup_totals_detail(self, matchup_key: str, away_team: str, home_team: str) -> None:
        if self.expanded_matchup_key == matchup_key:
            self.expanded_matchup_key = ""
            return

        self.expanded_matchup_key = matchup_key
        if matchup_key in self.matchup_totals_details:
            return

        slate_date = str(self.odds_status.get("slate_date", "") or "").strip() or None
        detail = get_matchup_totals_detail(
            away_team=away_team,
            home_team=home_team,
            slate_date=slate_date,
            force_refresh=False,
        )
        self.matchup_totals_details = {
            **self.matchup_totals_details,
            matchup_key: {
                str(key): "" if value is None else str(value)
                for key, value in detail.items()
            },
        }

    def refresh_matchup_totals_detail(self, matchup_key: str, away_team: str, home_team: str) -> None:
        slate_date = str(self.odds_status.get("slate_date", "") or "").strip() or None
        detail = get_matchup_totals_detail(
            away_team=away_team,
            home_team=home_team,
            slate_date=slate_date,
            force_refresh=True,
        )
        self.expanded_matchup_key = matchup_key
        self.matchup_totals_details = {
            **self.matchup_totals_details,
            matchup_key: {
                str(key): "" if value is None else str(value)
                for key, value in detail.items()
            },
        }

    def _runtime_value(self, item_name: str) -> str:
        for row in self.runtime_rows:
            if str(row.get("Item", "")).strip() == item_name:
                return str(row.get("Value", "")).strip()
        return ""

    def _data_health_value(self, item_name: str) -> str:
        for row in self.data_health_rows:
            if str(row.get("Item", "")).strip() == item_name:
                return str(row.get("Value", "")).strip()
        return ""

    @rx.var
    def model_simulation_count(self) -> str:
        raw_value = self._runtime_value("Default Sims")
        try:
            return f"{int(float(raw_value)):,}"
        except (TypeError, ValueError):
            return raw_value or "-"

    @rx.var
    def model_run_dispersion(self) -> str:
        raw_value = self._runtime_value("Run Dispersion")
        try:
            return f"{float(raw_value):.1f}"
        except (TypeError, ValueError):
            return raw_value or "-"

    @rx.var
    def model_database_status(self) -> str:
        raw_value = self._runtime_value("Database Exists").lower()
        return "Connected" if raw_value == "true" else "Not connected"

    @rx.var
    def data_games_loaded(self) -> str:
        return self._data_health_value("Games Loaded") or "0"

    @rx.var
    def data_stat_status(self) -> str:
        return self._data_health_value("MLB Stats Status") or "Missing"

    @rx.var
    def data_feature_status(self) -> str:
        feature_status = self._data_health_value("Feature Pipeline Status") or "Waiting"
        feature_rows = self._data_health_value("Feature Rows") or "0"
        return f"{feature_status} ({feature_rows})"

    @rx.var
    def data_weather_status(self) -> str:
        source = self._data_health_value("Weather Probe Source") or "Unavailable"
        team = self._data_health_value("Weather Probe Team") or "No slate loaded"
        return f"{source} | {team}"

    @rx.var
    def data_health_notes(self) -> list[dict[str, str]]:
        return [
            {
                "label": "Team Stats Rows",
                "value": self._data_health_value("Team Stats Rows") or "0",
                "helper": "Daily team stat rows available for feature engineering.",
            },
            {
                "label": "Pitcher Stats Rows",
                "value": self._data_health_value("Pitcher Stats Rows") or "0",
                "helper": "Pitcher history rows available for ERA, FIP, and bullpen-derived features.",
            },
            {
                "label": "Starting Pitchers",
                "value": self._data_health_value("Starting Pitchers Loaded") or "0",
                "helper": "Starter lookup rows saved in SQLite.",
            },
            {
                "label": "Prediction Rows",
                "value": self._data_health_value("Prediction Rows") or "0",
                "helper": "Saved probability outputs ready for downstream views.",
            },
            {
                "label": "Weather Probe",
                "value": self._data_health_value("Weather Probe Temp") or "-",
                "helper": self._data_health_value("Weather Probe Source") or "Unavailable",
            },
        ]

    @rx.var
    def odds_source_label(self) -> str:
        return str(self.odds_status.get("source", "CACHE") or "CACHE")

    @rx.var
    def odds_last_refreshed_label(self) -> str:
        return str(self.odds_status.get("last_refreshed_at", "Not refreshed yet") or "Not refreshed yet")

    @rx.var
    def odds_quota_label(self) -> str:
        remaining = str(self.odds_status.get("requests_remaining", "") or "").strip()
        used = str(self.odds_status.get("requests_used", "") or "").strip()
        credits_last = str(self.odds_status.get("credits_last", "") or "").strip()

        parts = []
        if remaining:
            parts.append(f"{remaining} credits left")
        if used:
            parts.append(f"{used} used")
        if credits_last:
            parts.append(f"last call cost {credits_last}")
        return " | ".join(parts) if parts else "Quota updates after paid odds requests."

    @rx.var
    def odds_refresh_note(self) -> str:
        error_message = str(self.odds_status.get("error_message", "") or "").strip()
        if error_message:
            return "Live odds are temporarily unavailable. The board is using cached data when possible."
        if str(self.odds_status.get("manual_only", "false")).lower() == "true":
            return "Low remaining credits detected. Automatic paid refreshes are disabled; use the refresh button only when you need a live update."
        return "Board odds load from cache when fresh. Refresh Data forces a live update and bypasses the local cache."

    @rx.var
    def performance_market_options(self) -> list[str]:
        return ["All", "Side", "Total"]

    @rx.var
    def performance_best_bet_options(self) -> list[str]:
        return ["All Bets", "Best Bet Only"]

    @rx.var
    def performance_actionability_options(self) -> list[str]:
        return ["All Rows", "Actionable Only", "Non-Actionable"]

    @rx.var
    def performance_tracking_mode_options(self) -> list[str]:
        return ["All Modes", "Full Visible Board", "Model Leans Only", "Actionable Only"]

    @rx.var
    def snapshot_tracking_mode_options(self) -> list[str]:
        return ["Full Visible Board", "Model Leans Only", "Actionable Only"]

    @rx.var
    def performance_edge_bucket_options(self) -> list[str]:
        return ["All Buckets", "8%+", "5-8%", "2-5%", "0-2%"]

    @rx.var
    def performance_date_range_options(self) -> list[str]:
        return ["All Dates", "Last 7 Days", "Last 30 Days"]

    @rx.var
    def filtered_performance_rows(self) -> list[dict[str, str]]:
        rows = list(self.performance_rows)
        if self.selected_performance_market == "Side":
            rows = [row for row in rows if row.get("Bet Type") == "Side"]
        elif self.selected_performance_market == "Total":
            rows = [row for row in rows if row.get("Bet Type") == "Total"]

        if self.performance_best_bet_only == "Best Bet Only":
            rows = [row for row in rows if row.get("Signal") == "Strong Bet"]

        if self.selected_performance_actionability == "Actionable Only":
            rows = [row for row in rows if row.get("_is_actionable") == "1"]
        elif self.selected_performance_actionability == "Non-Actionable":
            rows = [row for row in rows if row.get("_is_actionable") == "0"]

        if self.selected_performance_tracking_mode != "All Modes":
            target_mode = _tracking_mode_value(self.selected_performance_tracking_mode)
            rows = [row for row in rows if row.get("_tracking_mode") == target_mode]

        if self.selected_performance_edge_bucket != "All Buckets":
            rows = [
                row for row in rows
                if row.get("Edge Bucket") == self.selected_performance_edge_bucket
            ]

        if self.selected_performance_date_range != "All Dates":
            days_back = 7 if self.selected_performance_date_range == "Last 7 Days" else 30
            cutoff = (datetime.now() - timedelta(days=days_back)).date()
            filtered_rows = []
            for row in rows:
                row_date = pd.to_datetime(row.get("Date"), errors="coerce")
                if pd.isna(row_date):
                    continue
                if row_date.date() >= cutoff:
                    filtered_rows.append(row)
            rows = filtered_rows
        return rows

    @rx.var
    def performance_record_summary(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        win_count = sum(1 for row in rows if row.get("_result_raw") == "win")
        loss_count = sum(1 for row in rows if row.get("_result_raw") == "loss")
        push_count = sum(1 for row in rows if row.get("_result_raw") == "push")
        settled_count = sum(1 for row in rows if row.get("_result_raw") in {"win", "loss", "push"})
        open_count = sum(1 for row in rows if row.get("_result_raw") not in {"win", "loss", "push"})
        actionable_rows = [row for row in rows if row.get("_is_actionable") == "1"]
        actionable_wins = sum(1 for row in actionable_rows if row.get("_result_raw") == "win")
        actionable_losses = sum(1 for row in actionable_rows if row.get("_result_raw") == "loss")
        actionable_pushes = sum(1 for row in actionable_rows if row.get("_result_raw") == "push")
        actionable_record = (
            f"{actionable_wins}-{actionable_losses}-{actionable_pushes}"
            if actionable_rows else "-"
        )
        return [
            {"label": "W-L-P", "value": f"{win_count}-{loss_count}-{push_count}", "helper": "All tracked rows"},
            {"label": "Settled Bets", "value": str(settled_count), "helper": "Rows with final outcomes"},
            {"label": "Open Bets", "value": str(open_count), "helper": "Awaiting game results"},
            {"label": "Actionable Record", "value": actionable_record, "helper": "Lean / Strong Bet rows"},
        ]

    @rx.var
    def performance_edge_bucket_summary(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        buckets = ["8%+", "5-8%", "2-5%", "0-2%"]
        summary: list[dict[str, str]] = []
        for bucket in buckets:
            bucket_rows = [row for row in rows if row.get("_edge_bucket") == bucket]
            if not bucket_rows:
                summary.append({"bucket": bucket, "bets": "0", "win_rate": "-", "units": "-", "roi": "-"})
                continue
            settled = [row for row in bucket_rows if row.get("_result_raw") in {"win", "loss", "push"}]
            decisions = [row for row in settled if row.get("_result_raw") in {"win", "loss"}]
            win_rate = f"{(sum(1 for row in decisions if row.get('_result_raw') == 'win') / len(decisions)) * 100:.1f}%" if decisions else "-"
            units_total = sum(_safe_float(row.get("_units_raw")) or 0.0 for row in settled)
            roi = f"{(units_total / len(settled)) * 100:.1f}%" if settled else "-"
            summary.append(
                {
                    "bucket": bucket,
                    "bets": str(len(bucket_rows)),
                    "win_rate": win_rate,
                    "units": f"{units_total:+.2f}" if settled else "-",
                    "roi": roi,
                }
            )
        return summary

    @rx.var
    def performance_split_sides_totals_rows(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        return self._build_performance_split_rows(
            [
                ("Sides", [row for row in rows if row.get("_market_type") == "moneyline"]),
                ("Totals", [row for row in rows if row.get("_market_type") == "total"]),
            ]
        )

    def _build_performance_split_rows(self, slices: list[tuple[str, list[dict[str, str]]]]) -> list[dict[str, str]]:
        slice_rows: list[dict[str, str]] = []
        for label, group_rows in slices:
            settled = [row for row in group_rows if row.get("_result_raw") in {"win", "loss", "push"}]
            decisions = [row for row in settled if row.get("_result_raw") in {"win", "loss"}]
            wins = sum(1 for row in decisions if row.get("_result_raw") == "win")
            losses = sum(1 for row in decisions if row.get("_result_raw") == "loss")
            pushes = sum(1 for row in settled if row.get("_result_raw") == "push")
            win_rate = f"{(wins / len(decisions)) * 100:.1f}%" if decisions else "-"
            units_total = sum(_safe_float(row.get("_units_raw")) or 0.0 for row in settled)
            roi = f"{(units_total / len(settled)) * 100:.1f}%" if settled else "-"
            slice_rows.append(
                {
                    "label": label,
                    "count": str(len(group_rows)),
                    "record": f"{wins}-{losses}-{pushes}" if settled else "-",
                    "units": f"{units_total:+.2f}" if settled else "-",
                    "roi": roi,
                    "win_rate": win_rate,
                }
            )
        return slice_rows

    @rx.var
    def performance_split_actionability_rows(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        return self._build_performance_split_rows(
            [
                ("Actionable", [row for row in rows if row.get("_is_actionable") == "1"]),
                ("Non-Actionable", [row for row in rows if row.get("_is_actionable") == "0"]),
            ]
        )

    @rx.var
    def performance_split_tracking_mode_rows(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        return self._build_performance_split_rows(
            [
                ("Full Visible Board", [row for row in rows if row.get("_tracking_mode") == "full_visible_board"]),
                ("Model Leans Only", [row for row in rows if row.get("_tracking_mode") == "model_leans_only"]),
                ("Actionable Only", [row for row in rows if row.get("_tracking_mode") == "actionable_only"]),
            ]
        )

    @rx.var
    def performance_snapshot_groups(self) -> list[dict[str, str]]:
        rows = list(self.filtered_performance_rows)
        grouped: dict[str, dict[str, str]] = {}
        for row in rows:
            snapshot_key = str(row.get("_snapshot_timestamp", "")).strip()
            if not snapshot_key:
                snapshot_key = "unknown"
            group = grouped.setdefault(
                snapshot_key,
                {
                    "snapshot": row.get("Snapshot", "-"),
                    "note": row.get("_snapshot_note", ""),
                    "count": "0",
                    "rows_text": "",
                },
            )
            row_line = f"{row.get('Matchup', '')} | {row.get('Bet Type', '')} | {row.get('Pick', '')} | {row.get('Result', 'Open')}"
            existing_text = str(group["rows_text"]).strip()
            group["rows_text"] = f"{existing_text}\n{row_line}".strip() if existing_text else row_line
            group["count"] = str(int(group["count"]) + 1)
        grouped_rows = [
            {"snapshot_key": key, **value}
            for key, value in grouped.items()
        ]
        grouped_rows.sort(key=lambda item: item.get("snapshot_key", ""), reverse=True)
        return grouped_rows

    @rx.var
    def performance_trend_points(self) -> list[dict[str, str]]:
        settled_rows = [row for row in reversed(list(self.filtered_performance_rows)) if row.get("_result_raw") in {"win", "loss", "push"}]
        if not settled_rows:
            return []
        cumulative = 0.0
        values: list[float] = []
        for row in settled_rows:
            cumulative += _safe_float(row.get("_units_raw")) or 0.0
            values.append(cumulative)
        max_abs = max(max(abs(value) for value in values), 1.0)
        points: list[dict[str, str]] = []
        for idx, (row, value) in enumerate(zip(settled_rows, values), start=1):
            height = max(18.0, (abs(value) / max_abs) * 92.0)
            points.append(
                {
                    "label": str(idx),
                    "matchup": str(row.get("Matchup", "")),
                    "value": f"{value:+.2f}",
                    "height": f"{height:.1f}px",
                    "tone": "up" if value >= 0 else "down",
                }
            )
        return points

    @rx.var
    def filtered_matchups(self) -> list[dict[str, str]]:
        rows = list(self.matchup_rows)
        if self.selected_team != "All Teams":
            rows = [
                row
                for row in rows
                if row.get("Away") == self.selected_team or row.get("Home") == self.selected_team
            ]
        if self.selected_signal != "All Signals":
            rows = [
                row
                for row in rows
                if row.get("Bet Flag") == self.selected_signal or row.get("Total Bet Flag") == self.selected_signal
            ]
        return rows

    @rx.var
    def filtered_matchup_cards(self) -> list[dict[str, str]]:
        allowed_matchups = {
            f"{row.get('Away')} at {row.get('Home')}"
            for row in self.filtered_matchups
        }
        return [card for card in self.matchup_cards if card.get("matchup") in allowed_matchups]

    @rx.var
    def daily_matchup_decision_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        impact_items = list(self.today_impact_cards)
        test_matchups: list[str] = []
        if TEST_HIGHLIGHT_MODE:
            ranked_for_test = sorted(
                list(self.filtered_matchup_cards),
                key=_probability_gap,
                reverse=True,
            )
            test_matchups = [
                str(card.get("matchup", "")).strip()
                for card in ranked_for_test[:2]
            ]

        for card in self.filtered_matchup_cards:
            away_team = str(card.get("away_team", "")).strip()
            home_team = str(card.get("home_team", "")).strip()
            matchup_key = str(card.get("matchup", "")).strip()
            best_bet = str(card.get("best_bet", "")).strip()
            favorite = str(card.get("favorite", "")).strip()
            model_lean = favorite if best_bet in {"", "Pass"} else best_bet
            lean_is_away = model_lean == away_team
            fair_price = str(card.get("away_fair_ml" if lean_is_away else "home_fair_ml", "")).strip() or "-"
            market_price = str(card.get("away_market_ml" if lean_is_away else "home_market_ml", "")).strip()
            edge_cents = _edge_cents(fair_price, market_price)
            edge_display = f"+{edge_cents} cents" if edge_cents is not None and edge_cents > 0 else "No edge"
            ev_status = _ev_status_label(card, lean_is_away)
            status_label = _daily_status_label(card)
            has_market = str(card.get("market_available", "")).lower() == "true"
            is_positive_edge = ev_status == "Positive EV" and edge_cents is not None and edge_cents > 0

            driver_tags = [
                tag
                for tag in (_driver_tag_label(item, away_team, home_team) for item in impact_items)
                if tag
            ][:3]
            if not driver_tags:
                driver_tags = ["No major signal"]

            actionable_bucket = 3
            grid_state = "Waiting"
            grid_badge = "Waiting"
            if TEST_HIGHLIGHT_MODE and matchup_key in test_matchups:
                if matchup_key == test_matchups[0]:
                    actionable_bucket = 0
                    grid_state = "Best Bet"
                    grid_badge = "Best Bet"
                elif len(test_matchups) > 1 and matchup_key == test_matchups[1]:
                    actionable_bucket = 1
                    grid_state = "Positive EV"
                    grid_badge = "Positive EV"
                else:
                    actionable_bucket = 2
                    grid_state = "Lean" if status_label in {"Strong", "Lean"} else "No Edge"
                    grid_badge = grid_state
            elif is_positive_edge:
                actionable_bucket = 1
                grid_state = "Positive EV"
                grid_badge = "Positive EV"
            elif has_market:
                actionable_bucket = 2
                grid_state = "Lean" if status_label in {"Strong", "Lean"} else "No Edge"
                grid_badge = grid_state

            ev_value = _to_float(card.get("away_ev" if lean_is_away else "home_ev")) or 0.0
            model_edge = abs(_to_float(card.get("win_edge")) or 0.0)

            cards.append(
                {
                    **card,
                    "status_label": status_label,
                    "model_lean": model_lean or "-",
                    "fair_price": fair_price,
                    "market_price": market_price or "",
                    "edge_cents": edge_display,
                    "ev_status": ev_status,
                    "run_split": (
                        f"Runs: {card.get('away_abbr', away_team)} {card.get('away_runs_proj', '-')} | "
                        f"{card.get('home_abbr', home_team)} {card.get('home_runs_proj', '-')}"
                    ),
                    "driver_1": driver_tags[0] if len(driver_tags) > 0 else "",
                    "driver_2": driver_tags[1] if len(driver_tags) > 1 else "",
                    "driver_3": driver_tags[2] if len(driver_tags) > 2 else "",
                    "grid_state": grid_state,
                    "grid_badge": grid_badge,
                    "details_open": "true" if self.expanded_matchup_key == matchup_key else "false",
                    "totals_available": str(self.matchup_totals_details.get(matchup_key, {}).get("available", "false")).lower(),
                    "totals_headline": self.matchup_totals_details.get(matchup_key, {}).get("headline", "Totals market"),
                    "totals_subheadline": self.matchup_totals_details.get(matchup_key, {}).get("subheadline", ""),
                    "totals_market_line": self.matchup_totals_details.get(matchup_key, {}).get("market_line", "-"),
                    "totals_over_price": self.matchup_totals_details.get(matchup_key, {}).get("over_price", "-"),
                    "totals_under_price": self.matchup_totals_details.get(matchup_key, {}).get("under_price", "-"),
                    "totals_source": self.matchup_totals_details.get(matchup_key, {}).get("source", "CACHE"),
                    "totals_last_refreshed_at": self.matchup_totals_details.get(matchup_key, {}).get("last_refreshed_at", "Not refreshed yet"),
                    "totals_quota_note": self.matchup_totals_details.get(matchup_key, {}).get("quota_note", "Detailed odds load only when opened."),
                    "_sort_bucket": actionable_bucket,
                    "_sort_ev": f"{ev_value:.4f}",
                    "_sort_edge": f"{model_edge:.4f}",
                }
            )

        ranked_cards = sorted(
            cards,
            key=lambda item: (
                int(item.get("_sort_bucket", 2)),
                -float(item.get("_sort_ev", "0") or 0),
                -float(item.get("_sort_edge", "0") or 0),
            ),
        )
        if ranked_cards and not TEST_HIGHLIGHT_MODE:
            top_card = ranked_cards[0]
            if top_card.get("grid_state") == "Positive EV":
                top_card["grid_state"] = "Best Bet"
                top_card["grid_badge"] = "Best Bet"
                top_card["_sort_bucket"] = 0
        return ranked_cards

    @rx.var
    def top_bet_of_day(self) -> dict[str, str]:
        for card in self.daily_matchup_decision_cards:
            if card.get("grid_state") != "Best Bet":
                continue
            matchup = str(card.get("matchup_label", "")).strip()
            model_lean = str(card.get("model_lean", "")).strip()
            market_price = str(card.get("market_price", "")).strip()
            fair_price = str(card.get("fair_price", "")).strip()
            edge_cents = str(card.get("edge_cents", "")).strip()
            if not matchup or not model_lean:
                continue
            if market_price in {"", "undefined"}:
                continue
            if fair_price in {"", "-", "N/A", "undefined"}:
                continue
            if edge_cents in {"", "No edge", "undefined"}:
                continue
            return card
        return {}

    @rx.var
    def has_top_bet_of_day(self) -> bool:
        return bool(self.top_bet_of_day)

    @rx.var
    def featured_matchup_cards(self) -> list[dict[str, str]]:
        return self.filtered_matchup_cards[:4]

    @rx.var
    def projection_hero_cards(self) -> list[dict[str, str]]:
        rows = list(self.projected_rows)
        if not rows:
            return []
        best_team = rows[0]
        highest_wins = max(rows, key=lambda row: _to_float(row.get("Projected Wins")) or 0.0)
        strongest_offense = max(rows, key=lambda row: _to_float(row.get("Offense Score")) or 0.0)
        strongest_pitching = max(rows, key=lambda row: _to_float(row.get("Pitching Score")) or 0.0)
        return [
            {
                "label": "Best Team",
                "value": str(best_team.get("Team", "")).strip() or "-",
                "stat": f"{(_to_float(best_team.get('Projected Wins')) or 0.0):.1f} wins",
                "note": "Elite",
                "helper": "Cleanest full-season profile on the board.",
                "emphasis": "primary",
                "context": "#1 Overall Projection",
            },
            {
                "label": "Highest Projected Wins",
                "value": str(highest_wins.get("Team", "")).strip() or "-",
                "stat": f"{(_to_float(highest_wins.get('Projected Wins')) or 0.0):.1f} wins",
                "note": "Projected leader",
                "helper": "Best straight wins projection right now.",
                "emphasis": "primary",
                "context": "Top Wins Forecast",
            },
            {
                "label": "Strongest Offense",
                "value": str(strongest_offense.get("Team", "")).strip() or "-",
                "stat": f"Offense {_format_two_decimals(strongest_offense.get('Offense Score'))}",
                "note": "Top Unit",
                "helper": "Most dangerous run-scoring profile in the model.",
                "emphasis": "secondary",
                "context": "Run Creation",
            },
            {
                "label": "Strongest Pitching",
                "value": str(strongest_pitching.get("Team", "")).strip() or "-",
                "stat": f"Pitching {_format_two_decimals(strongest_pitching.get('Pitching Score'))}",
                "note": "Top Unit",
                "helper": "Best prevention profile across staff quality.",
                "emphasis": "secondary",
                "context": "Run Prevention",
            },
        ]

    @rx.var
    def projected_standings_view(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.projected_rows[:10]:
            rows.append(
                {
                    "Rank": str(row.get("Rank", "")),
                    "Team": str(row.get("Team", "")),
                    "Wins": f"{_to_float(row.get('Projected Wins')) or 0.0:.1f}",
                    "Win %": f"{_to_float(row.get('Projected Win %')) or 0.0:.3f}",
                }
            )
        return rows

    def _projection_tier_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {
                "rank": str(index + 1),
                "team": str(row.get("Team", "")).strip() or "-",
                "detail": f"{(_to_float(row.get('Projected Wins')) or 0.0):.1f} wins",
                "tag": _team_profile_descriptor(row),
            }
            for index, row in enumerate(rows)
        ]

    @rx.var
    def elite_projection_rows(self) -> list[dict[str, str]]:
        return self._projection_tier_rows(list(self.projected_rows)[:5])

    @rx.var
    def playoff_projection_rows(self) -> list[dict[str, str]]:
        return self._projection_tier_rows(list(self.projected_rows)[5:12])

    @rx.var
    def fringe_projection_rows(self) -> list[dict[str, str]]:
        return self._projection_tier_rows(list(self.projected_rows)[12:20])

    @rx.var
    def rebuilding_projection_rows(self) -> list[dict[str, str]]:
        return self._projection_tier_rows(list(self.projected_rows)[20:])

    @rx.var
    def current_outlook_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.current_rows[:3]:
            rows.append(
                {
                    "team": str(row.get("Team", "")).strip() or "-",
                    "detail": f"{str(row.get('Division', '')).strip()} | {str(row.get('Actual Wins', '')).strip()}-{str(row.get('Actual Losses', '')).strip()}",
                }
            )
        return rows

    @rx.var
    def playoff_outlook_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.playoff_rows[:3]:
            rows.append(
                {
                    "team": str(row.get("Team", "")).strip() or "-",
                    "detail": f"Playoff {_format_two_decimals(row.get('Playoff Odds'))}%",
                }
            )
        return rows

    def _division_standings_rows(self, division_name: str) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        projected_lookup = {
            str(row.get("Team", "")).strip(): row
            for row in self.projected_rows
        }
        division_rows = [
            row for row in self.current_rows
            if str(row.get("Division", "")).strip() == division_name
        ]
        division_rows = sorted(
            division_rows,
            key=lambda row: (
                -( _to_float(row.get("Actual Wins")) or 0.0),
                (_to_float(row.get("Actual Losses")) or 0.0),
                -( _to_float(row.get("Projected Wins")) or 0.0),
            ),
        )
        for row in division_rows:
            team_name = str(row.get("Team", "")).strip()
            projected_row = projected_lookup.get(team_name, {})
            actual_wins = int(_to_float(row.get("Actual Wins")) or 0)
            actual_losses = int(_to_float(row.get("Actual Losses")) or 0)
            projected_win_pct = _to_float(projected_row.get("Projected Win %")) or 0.0
            projected_wins_value = _to_float(projected_row.get("Projected Wins")) or 0.0
            projected_wins = int(round(projected_wins_value))
            projected_losses = max(0, 162 - projected_wins)
            rows.append(
                {
                    "Team": team_name or "-",
                    "Current": f"{actual_wins}-{actual_losses}",
                    "Projected": f"{projected_wins}-{projected_losses}",
                    "Current Win %": f"{(_to_float(row.get('Win %')) or 0.0):.3f}",
                    "Projected Win %": f"{projected_win_pct:.3f}",
                    "Outlook": str(row.get("Playoff Outlook", "")).strip() or "-",
                }
            )
        return rows

    @rx.var
    def al_east_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("AL East")

    @rx.var
    def al_central_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("AL Central")

    @rx.var
    def al_west_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("AL West")

    @rx.var
    def nl_east_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("NL East")

    @rx.var
    def nl_central_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("NL Central")

    @rx.var
    def nl_west_standings_rows(self) -> list[dict[str, str]]:
        return self._division_standings_rows("NL West")

    @rx.var
    def prediction_outlook_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.prediction_rows[:3]:
            rows.append(
                {
                    "team": f"{str(row.get('away_team', '')).strip()} @ {str(row.get('home_team', '')).strip()}",
                    "detail": f"Home {_format_two_decimals(row.get('home_win_prob'))} | Away {_format_two_decimals(row.get('away_win_prob'))}",
                }
            )
        return rows

    @rx.var
    def upcoming_prediction_table_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.upcoming_prediction_rows:
            away_team = str(row.get("away_team", "")).strip()
            home_team = str(row.get("home_team", "")).strip()
            recommended_side = str(row.get("recommended_side", "")).strip()
            recommended_bet = "Yes" if str(row.get("recommended_bet", "0")).strip() == "1" else "No"
            rows.append(
                {
                    "Date": str(row.get("game_date", "")).strip() or "-",
                    "Matchup": f"{away_team} @ {home_team}",
                    "Away Win %": f"{((_to_float(row.get('away_win_prob')) or 0.0) * 100):.1f}%",
                    "Home Win %": f"{((_to_float(row.get('home_win_prob')) or 0.0) * 100):.1f}%",
                    "Away Market %": "-" if _to_float(row.get("market_away_implied_prob_no_vig")) is None else f"{((_to_float(row.get('market_away_implied_prob_no_vig')) or 0.0) * 100):.1f}%",
                    "Home Market %": "-" if _to_float(row.get("market_home_implied_prob_no_vig")) is None else f"{((_to_float(row.get('market_home_implied_prob_no_vig')) or 0.0) * 100):.1f}%",
                    "Away Edge": "-" if _to_float(row.get("edge_away")) is None else f"{((_to_float(row.get('edge_away')) or 0.0) * 100):+.1f}%",
                    "Home Edge": "-" if _to_float(row.get("edge_home")) is None else f"{((_to_float(row.get('edge_home')) or 0.0) * 100):+.1f}%",
                    "Recommended": recommended_side or "-",
                    "Bet": recommended_bet,
                }
            )
        return rows

    @rx.var
    def driver_top_signal_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        preferred_order = [
            "Strongest Starter Edge",
            "Biggest Lineup Edge",
            "Highest Bullpen Risk",
        ]
        today_lookup = {
            str(item.get("headline") or item.get("label") or "").strip(): item
            for item in self.today_impact_cards
        }

        for label in preferred_order:
            item = today_lookup.get(label)
            if not item:
                continue
            cards.append(
                {
                    "label": label,
                    "value": str(item.get("team", "")).strip() or "-",
                    "stat": _round_number_in_text(str(item.get("metric") or item.get("value") or "-").strip()),
                    "note": _build_driver_note(
                        label,
                        str(item.get("metric") or item.get("value") or ""),
                        str(item.get("team", "") or ""),
                    ),
                }
            )

        if self.driver_model_movers:
            top_profile = self.driver_model_movers[0]
            cards.append(
                {
                    "label": "Best Team Profile",
                    "value": str(top_profile.get("Team", "")).strip() or "-",
                    "stat": str(top_profile.get("Model Driver", "")).strip() or "-",
                    "note": _build_driver_note(
                        "Best Team Profile",
                        str(top_profile.get("Model Driver", "") or ""),
                        str(top_profile.get("Team", "") or ""),
                    ),
                }
            )

        return cards[:4]

    @rx.var
    def driver_today_pitcher_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for row in self.driver_today_pitchers[:5]:
            cards.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "pitcher": str(row.get("Pitcher", "")).strip() or "-",
                    "matchup_line": (
                        f"{str(row.get('Team', '')).strip()} | {str(row.get('Matchup', '')).strip()}"
                    ).strip(" |")
                    or "-",
                    "metrics": (
                        f"Score: {_format_two_decimals(row.get('Pitcher Score'))} | "
                        f"FIP: {_format_two_decimals(row.get('FIP'))} | "
                        f"{str(row.get('Throws', '')).strip() or '-'}"
                    ),
                    "tier": _pitcher_tier(row.get("Rank", "")),
                }
            )
        return cards

    @rx.var
    def driver_pitcher_watch_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.driver_pitcher_watch[:8]:
            rows.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "primary": str(row.get("Pitcher", "")).strip() or "-",
                    "secondary": (
                        f"Score {_format_two_decimals(row.get('Pitcher Score'))} | "
                        f"FIP {_format_two_decimals(row.get('FIP'))} | "
                        f"{str(row.get('Throws', '')).strip() or '-'}"
                    ),
                    "tertiary": str(_pitcher_tier(row.get("Rank", ""))),
                }
            )
        return rows

    @rx.var
    def driver_best_bullpen_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.driver_bullpen_leaders[:5]:
            rows.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "primary": str(row.get("Team", "")).strip() or "-",
                    "secondary": f"Bullpen score {_format_two_decimals(row.get('Bullpen Score'))}",
                    "tertiary": _bullpen_status_label(str(row.get("Bullpen Status", ""))),
                }
            )
        return rows

    @rx.var
    def driver_risky_bullpen_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.driver_bullpen_stress[:5]:
            rows.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "primary": str(row.get("Team", "")).strip() or "-",
                    "secondary": f"Bullpen score {_format_two_decimals(row.get('Bullpen Score'))}",
                    "tertiary": _bullpen_status_label(str(row.get("Bullpen Status", ""))),
                }
            )
        return rows

    @rx.var
    def driver_lineup_rows(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for row in self.driver_lineups[:8]:
            confidence = str(row.get("Lineup Confidence", "")).strip() or "-"
            if confidence not in {"Full", "Thin"}:
                confidence = "Thin"
            rows.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "primary": str(row.get("Team", "")).strip() or "-",
                    "secondary": (
                        f"Score: {_format_two_decimals(row.get('Lineup Score'))} | "
                        f"Adj: {_format_two_decimals(row.get('Lineup Adjustment'))} | "
                        f"{confidence}"
                    ),
                    "tertiary": "",
                }
            )
        return rows

    @rx.var
    def driver_model_mover_cards(self) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        for row in self.driver_model_movers[:8]:
            cards.append(
                {
                    "rank": f"#{str(row.get('Rank', '-')).strip()}",
                    "team": str(row.get("Team", "")).strip() or "-",
                    "driver": str(row.get("Model Driver", "")).strip() or "-",
                    "metrics": (
                        f"Power: {_format_two_decimals(row.get('Power Score'))} | "
                        f"Offense: {_format_two_decimals(row.get('Offense Score'))} | "
                        f"Pitching: {_format_two_decimals(row.get('Pitching Score'))} | "
                        f"Bullpen: {_format_two_decimals(row.get('Bullpen Score'))}"
                    ),
                    "volatility": f"Volatility: {_volatility_label(row.get('Volatility Score'))}",
                }
            )
        return cards

    @rx.var
    def hero_games_value(self) -> str:
        if not self.summary_cards:
            return "-"
        return self.summary_cards[0].get("value", "-")

    @rx.var
    def hero_best_ev_value(self) -> str:
        if len(self.summary_cards) < 3:
            return "-"
        return self.summary_cards[2].get("value", "-")

    @rx.var
    def top_leans(self) -> list[dict[str, str]]:
        cards = list(self.matchup_cards)

        def lean_score(card: dict[str, str]) -> float:
            try:
                return abs(float(card.get("win_edge", "0") or 0))
            except (TypeError, ValueError):
                return 0.0

        ranked_cards = sorted(cards, key=lean_score, reverse=True)
        return ranked_cards[:3]

    @rx.var
    def top_lean_driver_groups(self) -> list[dict[str, str]]:
        groups: list[dict[str, str]] = []
        for card in self.top_leans:
            matchup = card.get("matchup", "")
            matching_drivers = [
                item
                for item in self.today_impact_cards
                if matchup and matchup in str(item.get("value", ""))
            ][:3]
            driver_lines = [_format_driver_line(item, matchup) for item in matching_drivers]
            win_edge = str(card.get("win_edge", "0")).strip() or "0"
            away_team = str(card.get("away_team", ""))
            home_team = str(card.get("home_team", ""))
            away_win = str(card.get("away_win", "")).strip()
            home_win = str(card.get("home_win", "")).strip()
            away_prob = coerce_probability(away_win)
            home_prob = coerce_probability(home_win)
            if away_prob is None or home_prob is None:
                print(f"Warning: missing Top Lean probability for {matchup}")
            groups.append(
                {
                    "matchup": matchup,
                    "matchup_label": format_matchup_label(away_team, home_team),
                    "favorite": card.get("favorite", ""),
                    "bet_flag": card.get("bet_flag", "Pass"),
                    "confidence_label": _confidence_label(win_edge),
                    "away_team": away_team,
                    "home_team": home_team,
                    "away_win": away_win,
                    "home_win": home_win,
                    "away_prob": "" if away_prob is None else f"{away_prob:.3f}",
                    "home_prob": "" if home_prob is None else f"{home_prob:.3f}",
                    "away_logo": card.get("away_logo", ""),
                    "home_logo": card.get("home_logo", ""),
                    "away_primary": card.get("away_primary", ""),
                    "home_primary": card.get("home_primary", ""),
                    "win_edge": win_edge,
                    "edge_display": f"+{win_edge}%",
                    "probability_line": format_matchup_probability_line(
                        away_team,
                        away_prob if away_prob is not None else away_win,
                        home_team,
                        home_prob if home_prob is not None else home_win,
                    ),
                    "projected_total": card.get("projected_total", ""),
                    "projected_score": card.get("projected_score", ""),
                    "best_bet": card.get("best_bet", "Pass"),
                    "driver_1": driver_lines[0] if len(driver_lines) > 0 else "",
                    "driver_2": driver_lines[1] if len(driver_lines) > 1 else "",
                    "driver_3": driver_lines[2] if len(driver_lines) > 2 else "",
                }
            )
        return groups
