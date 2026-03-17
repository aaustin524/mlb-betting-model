"""Grading and performance helper functions for the Streamlit dashboard."""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.tracked_bets import (
    build_graded_results_from_tracked_bets,
    load_tracked_bets_from_db,
    sync_graded_results_to_db,
)
from model.clv_tracker import calculate_side_clv_metrics, calculate_total_clv_metrics


def american_odds_profit(odds_value):
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


def grade_side_pick(row):
    best_bet = row.get("Best Bet")
    bet_flag = row.get("Bet Flag")
    final_away_runs = row.get("Final Away Runs")
    final_home_runs = row.get("Final Home Runs")

    if best_bet in {None, "Pass"} or pd.isna(best_bet) or bet_flag not in {"Lean", "Strong Bet"}:
        return None, "Ungraded", None, None
    if pd.isna(final_away_runs) or pd.isna(final_home_runs):
        return best_bet, "Ungraded", None, "missing final score"

    try:
        final_away_runs = float(final_away_runs)
        final_home_runs = float(final_home_runs)
    except (TypeError, ValueError):
        return best_bet, "Ungraded", None, "invalid score entry"

    if best_bet == row.get("Away"):
        price = row.get("Away Moneyline")
        if final_away_runs > final_home_runs:
            units = american_odds_profit(price)
            if units is None:
                return best_bet, "Ungraded", None, "missing side price"
            return best_bet, "Win", units, None
        if final_away_runs < final_home_runs:
            return best_bet, "Loss", -1.0, None
        return best_bet, "Push", 0.0, None

    if best_bet == row.get("Home"):
        price = row.get("Home Moneyline")
        if final_home_runs > final_away_runs:
            units = american_odds_profit(price)
            if units is None:
                return best_bet, "Ungraded", None, "missing side price"
            return best_bet, "Win", units, None
        if final_home_runs < final_away_runs:
            return best_bet, "Loss", -1.0, None
        return best_bet, "Push", 0.0, None

    return best_bet, "Ungraded", None, "invalid side pick"


def grade_total_pick(row):
    best_total_bet = row.get("Best Total Bet")
    total_bet_flag = row.get("Total Bet Flag")
    total_line = row.get("Total Line")
    final_away_runs = row.get("Final Away Runs")
    final_home_runs = row.get("Final Home Runs")

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
        price = row.get("Over Price")
        if final_total > total_line:
            units = american_odds_profit(price)
            if units is None:
                return best_total_bet, final_total, "Ungraded", None, "missing total price"
            return best_total_bet, final_total, "Win", units, None
        if final_total < total_line:
            return best_total_bet, final_total, "Loss", -1.0, None
        return best_total_bet, final_total, "Push", 0.0, None

    if best_total_bet == "Under":
        price = row.get("Under Price")
        if final_total < total_line:
            units = american_odds_profit(price)
            if units is None:
                return best_total_bet, final_total, "Ungraded", None, "missing total price"
            return best_total_bet, final_total, "Win", units, None
        if final_total > total_line:
            return best_total_bet, final_total, "Loss", -1.0, None
        return best_total_bet, final_total, "Push", 0.0, None

    return best_total_bet, final_total, "Ungraded", None, "invalid total pick"


def calculate_side_clv(row):
    clv_value, _ = calculate_side_clv_metrics(
        {
            "best_bet": row.get("Best Bet"),
            "away_team": row.get("Away"),
            "home_team": row.get("Home"),
            "open_away_ml": row.get("Away Moneyline"),
            "open_home_ml": row.get("Home Moneyline"),
            "close_away_ml": row.get("Closing Away Moneyline"),
            "close_home_ml": row.get("Closing Home Moneyline"),
        }
    )
    return clv_value


def calculate_total_clv(row):
    clv_value, _ = calculate_total_clv_metrics(
        {
            "best_total_bet": row.get("Best Total Bet"),
            "open_total": row.get("Total Line"),
            "close_total": row.get("Closing Total Line"),
            "open_over_price": row.get("Over Price"),
            "open_under_price": row.get("Under Price"),
            "close_over_price": row.get("Closing Over Price"),
            "close_under_price": row.get("Closing Under Price"),
        }
    )
    return clv_value


def build_graded_snapshot_dataframe(snapshot_df):
    graded_df = snapshot_df.copy()
    if "Final Away Runs" not in graded_df.columns:
        graded_df["Final Away Runs"] = None
    if "Final Home Runs" not in graded_df.columns:
        graded_df["Final Home Runs"] = None
    if "Closing Away Moneyline" not in graded_df.columns:
        graded_df["Closing Away Moneyline"] = None
    if "Closing Home Moneyline" not in graded_df.columns:
        graded_df["Closing Home Moneyline"] = None
    if "Closing Total Line" not in graded_df.columns:
        graded_df["Closing Total Line"] = None
    if "Closing Over Price" not in graded_df.columns:
        graded_df["Closing Over Price"] = None
    if "Closing Under Price" not in graded_df.columns:
        graded_df["Closing Under Price"] = None

    side_results = graded_df.apply(grade_side_pick, axis=1, result_type="expand")
    side_results.columns = ["Side Pick Result", "Side Pick Outcome", "Side Units", "Side Grading Note"]

    total_results = graded_df.apply(grade_total_pick, axis=1, result_type="expand")
    total_results.columns = [
        "Total Pick Result",
        "Final Total",
        "Total Pick Outcome",
        "Total Units",
        "Total Grading Note",
    ]

    graded_df = pd.concat([graded_df, side_results, total_results], axis=1)
    graded_df["grading_key"] = (
        graded_df["snapshot_timestamp"].astype(str)
        + "|"
        + graded_df["Away"].astype(str)
        + "|"
        + graded_df["Home"].astype(str)
    )
    graded_df["grading_note"] = (
        graded_df[["Side Grading Note", "Total Grading Note"]]
        .fillna("")
        .agg(" | ".join, axis=1)
        .str.strip(" |")
        .replace("", None)
    )
    graded_df["Side CLV"] = graded_df.apply(calculate_side_clv, axis=1)
    graded_df["Total CLV"] = graded_df.apply(calculate_total_clv, axis=1)
    graded_df["grading_status"] = graded_df.apply(
        lambda row: (
            "graded"
            if row.get("Side Pick Outcome") in {"Win", "Loss", "Push"}
            or row.get("Total Pick Outcome") in {"Win", "Loss", "Push"}
            else "ungraded"
        ),
        axis=1,
    )
    return graded_df


@st.cache_data(show_spinner=False)
def load_graded_results(graded_results_path):
    csv_results_df = pd.DataFrame()
    if os.path.exists(graded_results_path):
        try:
            csv_results_df = pd.read_csv(graded_results_path)
        except pd.errors.EmptyDataError:
            csv_results_df = pd.DataFrame()

    tracked_results_df = build_graded_results_from_tracked_bets(load_tracked_bets_from_db())
    combined_df = pd.concat([csv_results_df, tracked_results_df], ignore_index=True, sort=False)
    if combined_df.empty:
        return combined_df

    if "grading_key" in combined_df.columns:
        combined_df = combined_df.drop_duplicates(subset=["grading_key"], keep="last")
    return combined_df


def append_graded_results(graded_snapshot_df, graded_results_path, ensure_history_dir):
    ensure_history_dir()
    graded_rows_df = graded_snapshot_df[
        graded_snapshot_df["Side Pick Outcome"].isin(["Win", "Loss", "Push"])
        | graded_snapshot_df["Total Pick Outcome"].isin(["Win", "Loss", "Push"])
    ].copy()
    if graded_rows_df.empty:
        return 0

    graded_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    graded_rows_df["graded_timestamp"] = graded_now
    existing_df = load_graded_results(graded_results_path)
    combined_df = pd.concat([existing_df, graded_rows_df], ignore_index=True)
    if not combined_df.empty:
        combined_df = combined_df.drop_duplicates(subset=["grading_key"], keep="last")
    combined_df.to_csv(graded_results_path, index=False)
    sync_graded_results_to_db(graded_rows_df)
    load_graded_results.clear()
    return len(graded_rows_df)


def summarize_graded_results(graded_results_df):
    if graded_results_df is None or graded_results_df.empty:
        return None

    side_df = graded_results_df[graded_results_df["Side Pick Outcome"].isin(["Win", "Loss", "Push"])].copy()
    total_df = graded_results_df[graded_results_df["Total Pick Outcome"].isin(["Win", "Loss", "Push"])].copy()
    side_clv_series = pd.to_numeric(side_df.get("Side CLV"), errors="coerce")
    total_clv_series = pd.to_numeric(total_df.get("Total CLV"), errors="coerce")
    combined_clv_series = pd.concat([side_clv_series, total_clv_series], ignore_index=True).dropna()

    side_decision_df = side_df[side_df["Side Pick Outcome"].isin(["Win", "Loss"])]
    total_decision_df = total_df[total_df["Total Pick Outcome"].isin(["Win", "Loss"])]

    return {
        "total_graded_side_bets": len(side_df),
        "side_win_rate": (
            f"{(side_decision_df['Side Pick Outcome'].eq('Win').mean() * 100):.1f}%"
            if not side_decision_df.empty
            else "N/A"
        ),
        "side_units": f"{pd.to_numeric(side_df['Side Units'], errors='coerce').fillna(0).sum():+.2f}",
        "total_graded_total_bets": len(total_df),
        "total_win_rate": (
            f"{(total_decision_df['Total Pick Outcome'].eq('Win').mean() * 100):.1f}%"
            if not total_decision_df.empty
            else "N/A"
        ),
        "total_units": f"{pd.to_numeric(total_df['Total Units'], errors='coerce').fillna(0).sum():+.2f}",
        "combined_units": (
            f"{pd.to_numeric(side_df['Side Units'], errors='coerce').fillna(0).sum() + pd.to_numeric(total_df['Total Units'], errors='coerce').fillna(0).sum():+.2f}"
        ),
        "avg_side_clv": f"{side_clv_series.mean():+.2f}" if side_clv_series.notna().any() else "N/A",
        "avg_total_clv": f"{total_clv_series.mean():+.2f}" if total_clv_series.notna().any() else "N/A",
        "positive_clv_rate": (
            f"{(combined_clv_series.gt(0).mean() * 100):.1f}%"
            if not combined_clv_series.empty
            else "N/A"
        ),
    }
