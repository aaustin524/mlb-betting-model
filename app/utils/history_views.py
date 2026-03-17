"""History and grading Streamlit helpers for board snapshots."""

from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.performance_helpers import (
    append_graded_results,
    build_graded_snapshot_dataframe,
    load_graded_results,
)
from utils.tracked_bets import enrich_snapshot_with_tracked_bets, load_tracked_bets_from_db
from model.clv_tracker import auto_grade_tracked_bets


def ensure_history_dir(history_dir):
    os.makedirs(history_dir, exist_ok=True)
    return history_dir


def list_history_files(history_dir, prefix=None):
    if not os.path.isdir(history_dir):
        return []

    history_files = []
    for file_name in os.listdir(history_dir):
        if not file_name.endswith(".csv"):
            continue
        if prefix and not file_name.startswith(prefix):
            continue

        file_path = os.path.join(history_dir, file_name)
        try:
            modified_time = os.path.getmtime(file_path)
        except OSError:
            continue

        history_files.append(
            {
                "file_name": file_name,
                "file_path": file_path,
                "modified_time": modified_time,
            }
        )

    history_files.sort(key=lambda item: item["modified_time"], reverse=True)
    return history_files


@st.cache_data(show_spinner=False)
def load_history_snapshot(file_path):
    return pd.read_csv(file_path)


def _render_grading_status():
    grading_results_status = st.session_state.get("grading_results_status")
    if grading_results_status:
        status_level, status_message = grading_results_status
        if status_level == "success":
            st.success(status_message)
        elif status_level == "warning":
            st.warning(status_message)
        else:
            st.error(status_message)
        st.session_state.pop("grading_results_status", None)


def render_history_viewer(history_dir):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Board History</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Review saved board and top-play snapshots without changing the current live board.</div>',
        unsafe_allow_html=True,
    )

    board_files = list_history_files(history_dir, prefix="board_snapshot_")
    top_play_files = list_history_files(history_dir, prefix="top_plays_snapshot_")

    if not board_files and not top_play_files:
        st.info("No saved snapshots yet. Use Save Board Snapshot to create the first one.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    history_col_1, history_col_2 = st.columns(2)

    with history_col_1:
        if board_files:
            board_options = {
                f"{item['file_name']} | {datetime.fromtimestamp(item['modified_time']).strftime('%Y-%m-%d %H:%M:%S')}": item
                for item in board_files
            }
            selected_board_label = st.selectbox("Board Snapshots", options=list(board_options.keys()))
            selected_board = board_options[selected_board_label]
            try:
                board_snapshot_df = load_history_snapshot(selected_board["file_path"])
                summary_col_1, summary_col_2, summary_col_3 = st.columns(3)
                with summary_col_1:
                    st.metric("Games", len(board_snapshot_df))
                with summary_col_2:
                    playable_side_bets = int(
                        board_snapshot_df.get("Bet Flag", pd.Series(dtype=object)).isin(["Lean", "Strong Bet"]).sum()
                    )
                    st.metric("Playable Sides", playable_side_bets)
                with summary_col_3:
                    playable_total_bets = int(
                        board_snapshot_df.get("Total Bet Flag", pd.Series(dtype=object)).isin(["Lean", "Strong Bet"]).sum()
                    )
                    st.metric("Playable Totals", playable_total_bets)
                st.dataframe(board_snapshot_df, hide_index=True, use_container_width=True)
            except Exception as exc:
                st.error(f"Unable to load board snapshot: {exc}")
        else:
            st.info("No board snapshots saved yet.")

    with history_col_2:
        if top_play_files:
            top_play_options = {
                f"{item['file_name']} | {datetime.fromtimestamp(item['modified_time']).strftime('%Y-%m-%d %H:%M:%S')}": item
                for item in top_play_files
            }
            selected_top_play_label = st.selectbox("Top Play Snapshots", options=list(top_play_options.keys()))
            selected_top_play = top_play_options[selected_top_play_label]
            try:
                top_play_snapshot_df = load_history_snapshot(selected_top_play["file_path"])
                st.dataframe(top_play_snapshot_df, hide_index=True, use_container_width=True)
            except Exception as exc:
                st.error(f"Unable to load top plays snapshot: {exc}")
        else:
            st.info("No top plays snapshots saved yet.")

    st.markdown('</div>', unsafe_allow_html=True)


def render_results_grading(graded_results_path, history_dir):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Results Grading</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Auto-grade tracked bets from final game scores when available, or use the manual snapshot editor as an override.</div>',
        unsafe_allow_html=True,
    )

    action_col_1, action_col_2 = st.columns([1, 3])
    with action_col_1:
        if st.button("Auto Grade From DB", use_container_width=True):
            try:
                auto_grade_results = auto_grade_tracked_bets()
                load_tracked_bets_from_db.clear()
                load_graded_results.clear()
                st.session_state["grading_results_status"] = (
                    "success",
                    "Auto-graded "
                    f"{auto_grade_results['graded_rows']} tracked bets "
                    f"from {auto_grade_results['eligible_rows']} eligible completed games.",
                )
            except Exception as exc:
                st.session_state["grading_results_status"] = ("error", f"Auto grading failed: {exc}")
            st.rerun()
    with action_col_2:
        st.markdown(
            '<div class="toolbar-note">The automated grader only settles tracked bets that already have a linked <code>game_id</code> and official final scores in SQLite.</div>',
            unsafe_allow_html=True,
        )

    board_files = list_history_files(history_dir, prefix="board_snapshot_")
    if not board_files:
        _render_grading_status()
        st.info("No board snapshots available for manual grading yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    grading_options = {
        f"{item['file_name']} | {datetime.fromtimestamp(item['modified_time']).strftime('%Y-%m-%d %H:%M:%S')}": item
        for item in board_files
    }
    selected_label = st.selectbox(
        "Snapshot To Grade",
        options=list(grading_options.keys()),
        key="grading_snapshot_selector",
    )
    selected_snapshot = grading_options[selected_label]

    try:
        grading_source_df = enrich_snapshot_with_tracked_bets(load_history_snapshot(selected_snapshot["file_path"]))
    except Exception as exc:
        st.error(f"Unable to load grading snapshot: {exc}")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    grading_input_df = grading_source_df.copy()
    if "Final Away Runs" not in grading_input_df.columns:
        grading_input_df["Final Away Runs"] = None
    if "Final Home Runs" not in grading_input_df.columns:
        grading_input_df["Final Home Runs"] = None
    if "Closing Away Moneyline" not in grading_input_df.columns:
        grading_input_df["Closing Away Moneyline"] = None
    if "Closing Home Moneyline" not in grading_input_df.columns:
        grading_input_df["Closing Home Moneyline"] = None
    if "Closing Total Line" not in grading_input_df.columns:
        grading_input_df["Closing Total Line"] = None
    if "Closing Over Price" not in grading_input_df.columns:
        grading_input_df["Closing Over Price"] = grading_input_df.get("close_over_price")
    if "Closing Under Price" not in grading_input_df.columns:
        grading_input_df["Closing Under Price"] = grading_input_df.get("close_under_price")

    grading_editor_df = st.data_editor(
        grading_input_df[
            [
                "Away",
                "Home",
                "Best Bet",
                "Bet Flag",
                "Best Total Bet",
                "Total Bet Flag",
                "Total Line",
                "Closing Away Moneyline",
                "Closing Home Moneyline",
                "Closing Total Line",
                "Final Away Runs",
                "Final Home Runs",
            ]
        ],
        hide_index=True,
        use_container_width=True,
        disabled=[
            "Away",
            "Home",
            "Best Bet",
            "Bet Flag",
            "Best Total Bet",
            "Total Bet Flag",
            "Total Line",
        ],
        column_config={
            "Closing Away Moneyline": st.column_config.NumberColumn("Close Away ML", format="%d"),
            "Closing Home Moneyline": st.column_config.NumberColumn("Close Home ML", format="%d"),
            "Closing Total Line": st.column_config.NumberColumn("Close Total", format="%.1f"),
            "Final Away Runs": st.column_config.NumberColumn("Final Away", format="%d"),
            "Final Home Runs": st.column_config.NumberColumn("Final Home", format="%d"),
        },
        key=f"grading_editor_{selected_snapshot['file_name']}",
    )

    grading_preview_df = grading_source_df.copy()
    grading_preview_df["Closing Away Moneyline"] = grading_editor_df["Closing Away Moneyline"]
    grading_preview_df["Closing Home Moneyline"] = grading_editor_df["Closing Home Moneyline"]
    grading_preview_df["Closing Total Line"] = grading_editor_df["Closing Total Line"]
    grading_preview_df["Final Away Runs"] = grading_editor_df["Final Away Runs"]
    grading_preview_df["Final Home Runs"] = grading_editor_df["Final Home Runs"]
    if "Closing Over Price" not in grading_preview_df.columns:
        grading_preview_df["Closing Over Price"] = grading_input_df["Closing Over Price"]
    if "Closing Under Price" not in grading_preview_df.columns:
        grading_preview_df["Closing Under Price"] = grading_input_df["Closing Under Price"]

    graded_snapshot_df = build_graded_snapshot_dataframe(grading_preview_df)

    st.dataframe(
        graded_snapshot_df[
            [
                "Away",
                "Home",
                "Best Bet",
                "Side Pick Outcome",
                "Side Units",
                "Side CLV",
                "Best Total Bet",
                "Final Total",
                "Total Pick Outcome",
                "Total Units",
                "Total CLV",
                "grading_note",
                "grading_status",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    if st.button("Save Graded Results", use_container_width=False):
        try:
            saved_rows = append_graded_results(
                graded_snapshot_df,
                graded_results_path,
                lambda: ensure_history_dir(history_dir),
            )
            load_tracked_bets_from_db.clear()
            load_graded_results.clear()
            if saved_rows > 0:
                st.session_state["grading_results_status"] = (
                    "success",
                    f"Saved {saved_rows} graded row(s) from {selected_snapshot['file_name']}.",
                )
            else:
                st.session_state["grading_results_status"] = (
                    "warning",
                    "No fully graded rows were available to save yet.",
                )
        except Exception as exc:
            st.session_state["grading_results_status"] = ("error", f"Unable to save graded results: {exc}")
        st.rerun()

    _render_grading_status()
    st.markdown('</div>', unsafe_allow_html=True)
