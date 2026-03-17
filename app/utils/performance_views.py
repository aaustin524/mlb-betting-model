"""Streamlit render helpers for tracked-bet lifecycle, CLV, and performance."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.performance_helpers import load_graded_results, summarize_graded_results
from utils.season_monitor import _render_monitor_section_header
from utils.tracked_bets import (
    build_clv_market_records,
    build_tracked_bet_lifecycle_records,
    load_tracked_bets_from_db,
    summarize_clv_records,
    summarize_tracked_bet_lifecycle,
)
from model.clv_tracker import update_closing_lines


def _render_empty_state(title, message, checklist):
    """Render a clearer preseason/offseason empty state inside a section panel."""
    checklist_html = "".join(f"<li>{item}</li>" for item in checklist)
    st.markdown(
        f"""
        <div style="
            margin-top: 0.5rem;
            padding: 1rem 1.1rem;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            background:
                linear-gradient(135deg, rgba(18,24,38,0.96), rgba(10,14,24,0.96));
        ">
            <div style="
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #f7b267;
                margin-bottom: 0.45rem;
            ">{title}</div>
            <div style="
                color: rgba(255,255,255,0.86);
                line-height: 1.5;
                margin-bottom: 0.7rem;
            ">{message}</div>
            <ul style="
                margin: 0;
                padding-left: 1.1rem;
                color: rgba(255,255,255,0.72);
                line-height: 1.5;
            ">{checklist_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tracked_bet_lifecycle_summary():
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Tracked Bet Lifecycle</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Coverage monitor for linking, close-line capture, and grading across tracked bets.</div>',
        unsafe_allow_html=True,
    )

    tracked_bets_df = load_tracked_bets_from_db()
    lifecycle_df = build_tracked_bet_lifecycle_records(tracked_bets_df)
    summary = summarize_tracked_bet_lifecycle(lifecycle_df)
    if not summary:
        _render_empty_state(
            "Preseason / Offseason State",
            "Tracked bet lifecycle coverage will stay quiet until the board starts saving actionable bets with live markets.",
            [
                "Daily board snapshots can still be saved now, but no lifecycle coverage appears until games produce playable side or total flags.",
                "Once odds are live and tracked bets are stored, this section will monitor game linking, close-line capture, and grading coverage automatically.",
                "During the season, this panel becomes the best place to spot unlinked bets or missing close lines.",
            ],
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
    with metric_col_1:
        st.metric("Tracked Bets", summary["tracked_bets"])
        st.metric("Linked To Game", summary["linked_bets"])
    with metric_col_2:
        st.metric("Needs Link", summary["unlinked_bets"])
        st.metric("Close Lines Captured", summary["close_captured"])
    with metric_col_3:
        st.metric("Ready To Auto Grade", summary["eligible_for_auto_grade"])
        st.metric("Graded Bets", summary["graded_bets"])
    with metric_col_4:
        st.metric("Auto Graded", summary["auto_graded_bets"])
        st.metric("Manual Graded", summary["manual_graded_bets"])

    _render_monitor_section_header(
        "Grade Source Mix",
        "Breakdown of how resolved tracked bets were graded.",
    )
    grade_source_summary_df = summary["grade_source_summary"].copy()
    if grade_source_summary_df.empty:
        st.caption("No graded tracked bets are available yet.")
    else:
        st.dataframe(
            grade_source_summary_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Bets": st.column_config.NumberColumn("Bets", format="%d"),
            },
        )

    _render_monitor_section_header(
        "Recent Lifecycle Status",
        "Most recent tracked bets with linking, market-close, and grading coverage.",
    )
    recent_lifecycle_df = summary["recent_lifecycle"].copy()
    recent_lifecycle_df["Snapshot"] = pd.to_datetime(recent_lifecycle_df["Snapshot"], errors="coerce")
    recent_lifecycle_df["Snapshot"] = recent_lifecycle_df["Snapshot"].dt.strftime("%Y-%m-%d %H:%M").fillna("N/A")
    recent_lifecycle_df = recent_lifecycle_df.rename(
        columns={
            "game_match_method": "Match Method",
        }
    )
    st.dataframe(
        recent_lifecycle_df,
        hide_index=True,
        use_container_width=True,
    )

    st.markdown('</div>', unsafe_allow_html=True)


def render_clv_summary():
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">CLV Tracking</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Opening and closing line movement for tracked bets, using the SQLite snapshot workflow as the source of truth.</div>',
        unsafe_allow_html=True,
    )

    action_col_1, action_col_2 = st.columns([1, 3])
    with action_col_1:
        if st.button("Update Closing Lines", use_container_width=True):
            try:
                update_results = update_closing_lines()
                load_tracked_bets_from_db.clear()
                st.session_state["clv_update_status"] = (
                    "success",
                    "Updated "
                    f"{update_results['updated_rows']} tracked bets "
                    f"across {update_results['matched_markets']} matched live markets "
                    f"with {update_results['historical_rows']} historical backfills.",
                )
            except Exception as exc:
                st.session_state["clv_update_status"] = ("error", f"Closing line update failed: {exc}")
            st.rerun()
    with action_col_2:
        st.markdown(
            '<div class="toolbar-note">Use the updater after the market matures to refresh close lines and recalculate CLV automatically for unresolved tracked bets.</div>',
            unsafe_allow_html=True,
        )

    clv_update_status = st.session_state.get("clv_update_status")
    if clv_update_status:
        status_level, status_message = clv_update_status
        if status_level == "success":
            st.success(status_message)
        else:
            st.error(status_message)
        st.session_state.pop("clv_update_status", None)

    tracked_bets_df = load_tracked_bets_from_db()
    clv_records_df = build_clv_market_records(tracked_bets_df)
    summary = summarize_clv_records(clv_records_df)
    if not summary:
        _render_empty_state(
            "Waiting For Market History",
            "CLV tracking needs an opening snapshot and a later closing line update, so preseason boards will usually stay empty here.",
            [
                "Save a Daily Board snapshot once real market odds are available.",
                "Run the closing-line updater later in the day to capture the mature market.",
                "After that, this section will show average side CLV, totals CLV, beat-close rate, and the recent trend table.",
            ],
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
    with metric_col_1:
        avg_side_clv = summary["avg_side_clv"]
        st.metric("Average Side CLV", f"{avg_side_clv:+.2f}" if avg_side_clv is not None else "N/A")
    with metric_col_2:
        avg_total_clv = summary["avg_total_clv"]
        st.metric("Average Total CLV", f"{avg_total_clv:+.2f}" if avg_total_clv is not None else "N/A")
    with metric_col_3:
        beat_close_pct = summary["beat_close_pct"]
        st.metric("Percent Beating Close", f"{beat_close_pct:.1f}%" if beat_close_pct is not None else "N/A")
    with metric_col_4:
        st.metric("Tracked CLV Bets", len(clv_records_df))

    _render_monitor_section_header(
        "CLV By Market Type",
        "Average CLV and beat-close rate split between side bets and totals.",
    )
    market_type_summary_df = summary["market_type_summary"].copy()
    market_type_summary_df["Beat_Close_Rate"] = market_type_summary_df["Beat_Close_Rate"] * 100.0
    st.dataframe(
        market_type_summary_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Bets": st.column_config.NumberColumn("Bets", format="%d"),
            "Avg_CLV": st.column_config.NumberColumn("Avg CLV", format="%.2f"),
            "Beat_Close_Rate": st.column_config.NumberColumn("Beat Close %", format="%.1f"),
        },
    )

    _render_monitor_section_header(
        "Recent 20-Bet CLV Trend",
        "Most recent tracked CLV records across sides and totals.",
    )
    recent_20_df = summary["recent_20"].copy()
    recent_20_df["Closed"] = recent_20_df["Closed"].dt.strftime("%Y-%m-%d %H:%M").fillna("N/A")
    recent_20_df["Beat Close"] = recent_20_df["Beat Close"].map({True: "Yes", False: "No"})
    st.dataframe(
        recent_20_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "CLV": st.column_config.NumberColumn("CLV", format="%.2f"),
        },
    )

    st.markdown('</div>', unsafe_allow_html=True)


def render_performance_summary(graded_results_path):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Performance Summary</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Simple tracked results from locally graded board snapshots.</div>',
        unsafe_allow_html=True,
    )

    try:
        graded_results_df = load_graded_results(graded_results_path)
    except Exception as exc:
        st.error(f"Unable to load graded results: {exc}")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    if graded_results_df.empty:
        _render_empty_state(
            "No Settled Results Yet",
            "Performance stays empty until tracked bets or saved snapshots have final scores and grading outcomes.",
            [
                "This is expected before Opening Day or anytime the current season has no completed bets yet.",
                "Automatic grading will populate this section once linked games finish and results are written back to tracked bets.",
                "Manual snapshot grading remains available in Workflow Tools if you want to backfill older boards.",
            ],
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    summary = summarize_graded_results(graded_results_df)
    if not summary:
        _render_empty_state(
            "Grades In Progress",
            "Board history exists, but there are not enough settled bet outcomes yet to build a full performance summary.",
            [
                "Once side or total picks resolve as wins, losses, or pushes, this summary will populate automatically.",
                "CLV averages and unit totals will update as soon as closing lines and final scores are available.",
                "If this persists during the season, check Workflow Tools for pending grading or missing final scores.",
            ],
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
    with metric_col_1:
        st.metric("Graded Side Bets", summary["total_graded_side_bets"])
        st.metric("Side Win Rate", summary["side_win_rate"])
        st.metric("Avg Side CLV", summary["avg_side_clv"])
    with metric_col_2:
        st.metric("Side Units", summary["side_units"])
        st.metric("Graded Total Bets", summary["total_graded_total_bets"])
        st.metric("Avg Total CLV", summary["avg_total_clv"])
    with metric_col_3:
        st.metric("Total Win Rate", summary["total_win_rate"])
        st.metric("Total Units", summary["total_units"])
        st.metric("Combined Units", summary["combined_units"])
        st.metric("Positive CLV", summary["positive_clv_rate"])

    st.markdown('</div>', unsafe_allow_html=True)
