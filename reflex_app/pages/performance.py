from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import (
    dashboard_kpi_card,
    dashboard_section_header,
    dashboard_surface_card,
    intentional_empty_state,
)
from reflex_app.components.shell import page_shell
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def _tone_badge(label: str, tone: str) -> rx.Component:
    tone_styles = {
        "neutral": ("rgba(15, 23, 42, 0.05)", COLORS["light_muted"], "rgba(15, 23, 42, 0.10)"),
        "accent": (COLORS["light_accent_soft"], COLORS["light_accent"], "rgba(37, 99, 235, 0.16)"),
        "success": (COLORS["light_success_soft"], COLORS["light_success"], "rgba(15, 159, 110, 0.18)"),
        "danger": ("rgba(239, 68, 68, 0.10)", "#b91c1c", "rgba(239, 68, 68, 0.18)"),
        "warning": ("rgba(245, 158, 11, 0.10)", "#b45309", "rgba(245, 158, 11, 0.18)"),
    }
    background, color, border = tone_styles.get(tone, tone_styles["neutral"])
    return rx.box(
        label,
        padding="0.26rem 0.62rem",
        border_radius="999px",
        background=background,
        color=color,
        border=f"1px solid {border}",
        font_size="0.72rem",
        font_weight="700",
        white_space="nowrap",
    )


def _result_badge(result: str) -> rx.Component:
    tone = {
        "Win": "success",
        "Loss": "danger",
        "Push": "accent",
        "Open": "neutral",
    }.get(result, "neutral")
    return _tone_badge(result, tone)


def _signal_badge(signal: str, actionability: str) -> rx.Component:
    return rx.cond(
        actionability == "Non-Actionable",
        _tone_badge("Model Only", "neutral"),
        rx.cond(
            signal == "Strong Bet",
            _tone_badge("Best Bet", "success"),
            rx.cond(
                signal == "Lean",
                _tone_badge("Lean", "accent"),
                _tone_badge("Actionable", "warning"),
            ),
        ),
    )


def _performance_delete_row(row: dict[str, str]) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(
                f"{row['Date']} • {row['Matchup']}",
                font_size="0.84rem",
                font_weight="800",
                color=COLORS["light_text"],
            ),
            rx.text(
                f"{row['Bet Type']} | {row['Pick']} | {row['Locked Odds']}",
                font_size="0.78rem",
                color=COLORS["light_muted"],
            ),
            rx.cond(
                row["Note"] == "",
                rx.fragment(),
                rx.text(
                    row["Note"],
                    font_size="0.76rem",
                    color=COLORS["light_muted_2"],
                    font_style="italic",
                ),
            ),
            spacing="1",
            align="start",
        ),
        rx.spacer(),
        rx.button(
            "Delete",
            on_click=lambda: AppState.delete_performance_row(row["_performance_bet_id"]),
            background="rgba(239, 68, 68, 0.08)",
            color="#991b1b",
            border="1px solid rgba(239, 68, 68, 0.18)",
            border_radius="11px",
            padding="0.5rem 0.8rem",
            font_weight="700",
            _hover={"background": "rgba(239, 68, 68, 0.12)"},
        ),
        width="100%",
        align="center",
        padding="0.78rem 0.9rem",
        background=COLORS["light_panel_alt"],
        border=f"1px solid {COLORS['light_border']}",
        border_radius="16px",
    )


def _record_chip(item: dict[str, str]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                item["label"],
                font_size="0.70rem",
                letter_spacing="0.12em",
                text_transform="uppercase",
                color=COLORS["light_muted_2"],
                font_weight="700",
            ),
            rx.text(item["value"], font_size="1.08rem", font_weight="900", color=COLORS["light_text"]),
            rx.text(item["helper"], font_size="0.78rem", color=COLORS["light_muted"]),
            spacing="1",
            align="start",
        ),
        padding="0.86rem 0.95rem",
        background=COLORS["light_panel_alt"],
        border=f"1px solid {COLORS['light_border']}",
        border_radius="18px",
        width="100%",
    )


def _edge_bucket_row(row: dict[str, str]) -> rx.Component:
    return rx.grid(
        rx.text(row["bucket"], font_size="0.86rem", font_weight="800", color=COLORS["light_text"]),
        rx.text(f"{row['bets']} bets", font_size="0.8rem", color=COLORS["light_muted"]),
        rx.text(row["win_rate"], font_size="0.8rem", color=COLORS["light_muted"]),
        rx.text(row["units"], font_size="0.82rem", font_weight="700", color=COLORS["light_text"]),
        rx.text(row["roi"], font_size="0.8rem", color=COLORS["light_muted"]),
        columns="5",
        spacing="3",
        width="100%",
        padding="0.72rem 0",
        border_bottom=f"1px solid {COLORS['light_border']}",
        align="center",
    )


def _split_summary_card(title: str, rows: list[dict[str, str]]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(
                title,
                font_size="0.80rem",
                letter_spacing="0.14em",
                text_transform="uppercase",
                color=COLORS["light_muted_2"],
                font_weight="700",
            ),
            rx.vstack(
                rx.foreach(
                    rows,
                    lambda row: rx.grid(
                        rx.vstack(
                            rx.text(row["label"], font_size="0.84rem", font_weight="800", color=COLORS["light_text"]),
                            rx.text(f"{row['count']} tracked", font_size="0.76rem", color=COLORS["light_muted"]),
                            spacing="0",
                            align="start",
                        ),
                        rx.text(row["record"], font_size="0.8rem", color=COLORS["light_muted"]),
                        rx.text(row["win_rate"], font_size="0.8rem", color=COLORS["light_muted"]),
                        rx.text(row["units"], font_size="0.82rem", font_weight="700", color=COLORS["light_text"]),
                        rx.text(row["roi"], font_size="0.8rem", color=COLORS["light_muted"]),
                        columns="5",
                        spacing="3",
                        width="100%",
                        align="center",
                        padding="0.68rem 0",
                        border_bottom=f"1px solid {COLORS['light_border']}",
                    ),
                ),
                spacing="0",
                width="100%",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        padding="0.95rem",
        background=COLORS["light_panel_alt"],
        border=f"1px solid {COLORS['light_border']}",
        border_radius="18px",
        width="100%",
    )


def _trend_chart(points: list[dict[str, str]]) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.foreach(
                points,
                lambda point: rx.vstack(
                    rx.box(
                        width="100%",
                        height=point["height"],
                        border_radius="999px",
                        background=rx.cond(
                            point["tone"] == "up",
                            "linear-gradient(180deg, rgba(15,159,110,0.18) 0%, rgba(15,159,110,0.60) 100%)",
                            "linear-gradient(180deg, rgba(239,68,68,0.14) 0%, rgba(239,68,68,0.54) 100%)",
                        ),
                        border=rx.cond(
                            point["tone"] == "up",
                            "1px solid rgba(15,159,110,0.18)",
                            "1px solid rgba(239,68,68,0.16)",
                        ),
                    ),
                    rx.text(point["value"], font_size="0.73rem", color=COLORS["light_muted"], font_weight="700"),
                    rx.text(point["label"], font_size="0.70rem", color=COLORS["light_muted_2"]),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
            ),
            spacing="3",
            align="end",
            width="100%",
            min_height="150px",
        ),
        width="100%",
        padding="1rem 0.4rem 0.2rem 0.4rem",
    )


def _snapshot_group_card(group: dict[str, object]) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text(
                        str(group["snapshot"]),
                        font_size="0.88rem",
                        font_weight="800",
                        color=COLORS["light_text"],
                    ),
                    rx.text(
                        f"{group['count']} tracked row(s)",
                        font_size="0.78rem",
                        color=COLORS["light_muted"],
                    ),
                    spacing="0",
                    align="start",
                ),
                rx.spacer(),
                _tone_badge("Snapshot Batch", "accent"),
                width="100%",
                align="start",
            ),
            rx.cond(
                group["note"] == "",
                rx.fragment(),
                rx.box(
                    rx.text(
                        str(group["note"]),
                        font_size="0.82rem",
                        color=COLORS["light_muted"],
                        font_style="italic",
                    ),
                    width="100%",
                    padding="0.72rem 0.82rem",
                    background=COLORS["light_panel"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="14px",
                ),
            ),
            rx.vstack(
                rx.foreach(
                    group["rows_text"].split("\n"),
                    lambda row_line: rx.text(
                        row_line,
                        font_size="0.79rem",
                        color=COLORS["light_text"],
                        width="100%",
                        padding="0.58rem 0",
                        border_bottom=f"1px solid {COLORS['light_border']}",
                    ),
                ),
                spacing="0",
                width="100%",
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        padding="0.95rem",
        background=COLORS["light_panel_alt"],
        border=f"1px solid {COLORS['light_border']}",
        border_radius="18px",
        width="100%",
    )


def _performance_results_table(rows: list[dict[str, str]]) -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Snapshot", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                    rx.table.column_header_cell("Matchup", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                    rx.table.column_header_cell("Bet", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                    rx.table.column_header_cell("Odds", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                    rx.table.column_header_cell("Model", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                    rx.table.column_header_cell("Status", color=COLORS["light_muted_2"], font_size="0.72rem", text_transform="uppercase", border_bottom="1px solid rgba(15, 23, 42, 0.06)", background=COLORS["light_panel_alt"], padding="0.74rem 0.82rem"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    rows,
                    lambda row, idx: rx.table.row(
                        rx.table.cell(
                            rx.vstack(
                                rx.text(row["Snapshot"], font_size="0.79rem", font_weight="700", color=COLORS["light_text"]),
                                rx.text(row["Date"], font_size="0.74rem", color=COLORS["light_muted"]),
                                spacing="0",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        rx.table.cell(
                            rx.vstack(
                                rx.text(row["Matchup"], font_size="0.84rem", font_weight="800", color=COLORS["light_text"]),
                                rx.cond(
                                    row["Note"] == "",
                                    rx.hstack(
                                        rx.text(row["Tracking Mode"], font_size="0.75rem", color=COLORS["light_muted"]),
                                        _signal_badge(row["Signal"], row["Actionability"]),
                                        spacing="2",
                                        align="center",
                                        width="100%",
                                    ),
                                    rx.text(row["Note"], font_size="0.75rem", color=COLORS["light_muted"], font_style="italic"),
                                ),
                                spacing="0",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        rx.table.cell(
                            rx.vstack(
                                rx.text(f"{row['Bet Type']} • {row['Pick']}", font_size="0.82rem", font_weight="700", color=COLORS["light_text"]),
                                rx.hstack(
                                    _signal_badge(row["Signal"], row["Actionability"]),
                                    rx.cond(
                                        row["Actionability"] == "Non-Actionable",
                                        rx.fragment(),
                                        _tone_badge(row["Actionability"], "accent"),
                                    ),
                                    spacing="2",
                                    align="center",
                                    width="100%",
                                ),
                                spacing="0",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        rx.table.cell(
                            rx.vstack(
                                rx.text(f"Locked {row['Locked Odds']}", font_size="0.82rem", font_weight="700", color=COLORS["light_text"]),
                                rx.text(row["Bet Type"], font_size="0.74rem", color=COLORS["light_muted"]),
                                spacing="0",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        rx.table.cell(
                            rx.vstack(
                                rx.text(f"Edge {row['Model Edge']}", font_size="0.8rem", color=COLORS["light_text"]),
                                rx.text(f"EV {row['EV']}", font_size="0.74rem", color=COLORS["light_muted"]),
                                spacing="0",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        rx.table.cell(
                            rx.vstack(
                                _result_badge(row["Result"]),
                                rx.text(f"Units {row['Units']}", font_size="0.74rem", color=COLORS["light_muted"]),
                                spacing="1",
                                align="start",
                            ),
                            padding="0.88rem 0.82rem",
                        ),
                        background=rx.cond(idx % 2 == 0, COLORS["light_panel"], COLORS["light_panel_alt"]),
                        transition="all 160ms ease",
                        _hover={
                            "background": "#f4f8fc",
                            "box_shadow": "inset 0 0 0 1px rgba(15, 23, 42, 0.02)",
                        },
                    ),
                )
            ),
            variant="surface",
            size="2",
            width="100%",
            min_width="1180px",
        ),
        type="always",
        scrollbars="horizontal",
        style={
            "width": "100%",
            "border_radius": "16px",
            "border": f"1px solid {COLORS['light_border']}",
            "background": COLORS["light_panel"],
            "overflow": "hidden",
            "max_width": "100%",
            "box_shadow": "inset 0 1px 0 rgba(255,255,255,0.7)",
        },
    )


def performance_page() -> rx.Component:
    return page_shell(
        "Performance",
        "Manual paper-tracking workspace for locking model signals, grading results later, and measuring win rate, units, and ROI over time.",
        rx.box(
            rx.vstack(
                dashboard_surface_card(
                    rx.hstack(
                        dashboard_section_header(
                            "Paper Tracking",
                            "Lock the current board when you want to preserve the opening line, then grade the saved paper bets once final scores are available.",
                            "Workflow",
                        ),
                        rx.spacer(),
                        rx.hstack(
                            rx.vstack(
                                rx.text(
                                    "Snapshot Mode",
                                    font_size="0.72rem",
                                    letter_spacing="0.14em",
                                    text_transform="uppercase",
                                    color=COLORS["light_muted_2"],
                                    font_weight="700",
                                ),
                                rx.select(
                                    AppState.snapshot_tracking_mode_options,
                                    value=AppState.selected_snapshot_tracking_mode,
                                    on_change=AppState.set_selected_snapshot_tracking_mode,
                                    width="220px",
                                    variant="surface",
                                    background=COLORS["light_panel"],
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    color=COLORS["light_text"],
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text(
                                    "Optional Note",
                                    font_size="0.72rem",
                                    letter_spacing="0.14em",
                                    text_transform="uppercase",
                                    color=COLORS["light_muted_2"],
                                    font_weight="700",
                                ),
                                rx.input(
                                    value=AppState.snapshot_note_input,
                                    on_change=AppState.set_snapshot_note_input,
                                    placeholder="Why you saved this slate",
                                    width="260px",
                                    background=COLORS["light_panel"],
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    color=COLORS["light_text"],
                                    border_radius="12px",
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.button(
                                "Save Board Snapshot",
                                on_click=AppState.lock_snapshot,
                                background=COLORS["light_panel"],
                                color=COLORS["light_text"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                border_radius="12px",
                                padding="0.68rem 0.92rem",
                                font_weight="700",
                                _hover={"background": COLORS["light_panel_alt"]},
                            ),
                            rx.button(
                                "Grade Results",
                                on_click=AppState.grade_performance_results,
                                background=COLORS["light_panel"],
                                color=COLORS["light_text"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                border_radius="12px",
                                padding="0.68rem 0.92rem",
                                font_weight="700",
                                _hover={"background": COLORS["light_panel_alt"]},
                            ),
                            spacing="2",
                            flex_wrap="wrap",
                            justify="end",
                        ),
                        width="100%",
                        align="start",
                        spacing="3",
                        flex_wrap="wrap",
                    ),
                    rx.cond(
                        AppState.performance_notice == "",
                        rx.fragment(),
                        rx.box(
                            rx.text(
                                AppState.performance_notice,
                                font_size="0.82rem",
                                color=COLORS["light_muted"],
                                line_height="1.45",
                            ),
                            width="100%",
                            padding="0.8rem 0.88rem",
                            background=COLORS["light_panel_alt"],
                            border=f"1px solid {COLORS['light_border']}",
                            border_radius="16px",
                        ),
                    ),
                ),
                rx.grid(
                    rx.foreach(
                        AppState.performance_summary_cards,
                        lambda card: dashboard_kpi_card(card["label"], card["value"], card["delta"]),
                    ),
                    columns=rx.breakpoints(initial="1", sm="2", xl="3"),
                    spacing="4",
                    width="100%",
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Record Summary",
                        "Quick validation strip for how the saved board is settling against the lines you originally captured.",
                        "Validation View",
                    ),
                    rx.grid(
                        rx.foreach(AppState.performance_record_summary, _record_chip),
                        columns=rx.breakpoints(initial="1", sm="2", xl="4"),
                        spacing="3",
                        width="100%",
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Tracked Results",
                        "Review locked paper bets, filter the history, and track outcomes against the lines you originally saved.",
                        "History",
                    ),
                    rx.grid(
                        rx.vstack(
                            rx.text("Bet Type", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_market_options,
                                value=AppState.selected_performance_market,
                                on_change=AppState.set_selected_performance_market,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Signal Filter", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_best_bet_options,
                                value=AppState.performance_best_bet_only,
                                on_change=AppState.set_performance_best_bet_only,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Actionability", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_actionability_options,
                                value=AppState.selected_performance_actionability,
                                on_change=AppState.set_selected_performance_actionability,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Snapshot Mode", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_tracking_mode_options,
                                value=AppState.selected_performance_tracking_mode,
                                on_change=AppState.set_selected_performance_tracking_mode,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Edge Bucket", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_edge_bucket_options,
                                value=AppState.selected_performance_edge_bucket,
                                on_change=AppState.set_selected_performance_edge_bucket,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Date Range", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.select(
                                AppState.performance_date_range_options,
                                value=AppState.selected_performance_date_range,
                                on_change=AppState.set_selected_performance_date_range,
                                width="100%",
                                variant="surface",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border_strong']}",
                                color=COLORS["light_text"],
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        columns=rx.breakpoints(initial="1", md="2", xl="6"),
                        spacing="3",
                        width="100%",
                    ),
                    rx.cond(
                        AppState.filtered_performance_rows.length() == 0,
                        intentional_empty_state(
                            "No tracked paper bets match the current filters.",
                            "Lock a snapshot from Daily Matchups, then return here to review and grade the saved paper bets.",
                        ),
                        _performance_results_table(AppState.filtered_performance_rows),
                    ),
                ),
                rx.grid(
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Edge Bucket Performance",
                            "See how results are behaving across the model's edge ranges.",
                            "Bucket View",
                        ),
                        rx.vstack(
                            rx.grid(
                                rx.text("Bucket", font_size="0.70rem", color=COLORS["light_muted_2"], text_transform="uppercase", font_weight="700"),
                                rx.text("Bets", font_size="0.70rem", color=COLORS["light_muted_2"], text_transform="uppercase", font_weight="700"),
                                rx.text("Win Rate", font_size="0.70rem", color=COLORS["light_muted_2"], text_transform="uppercase", font_weight="700"),
                                rx.text("Units", font_size="0.70rem", color=COLORS["light_muted_2"], text_transform="uppercase", font_weight="700"),
                                rx.text("ROI", font_size="0.70rem", color=COLORS["light_muted_2"], text_transform="uppercase", font_weight="700"),
                                columns="5",
                                spacing="3",
                                width="100%",
                            ),
                            rx.foreach(AppState.performance_edge_bucket_summary, _edge_bucket_row),
                            spacing="0",
                            width="100%",
                        ),
                    ),
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Trend",
                            "Cumulative units for the current filtered view.",
                            "Performance Curve",
                        ),
                        rx.cond(
                            AppState.performance_trend_points.length() == 0,
                            intentional_empty_state(
                                "No settled rows are available for a trend line yet.",
                                "Once tracked rows settle, cumulative units will appear here.",
                            ),
                            _trend_chart(AppState.performance_trend_points),
                        ),
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Split Summaries",
                        "Compare results across market type, actionability, and snapshot mode without leaving the filtered view.",
                        "Breakdowns",
                    ),
                    rx.grid(
                        _split_summary_card("Sides vs Totals", AppState.performance_split_sides_totals_rows),
                        _split_summary_card("Actionable Split", AppState.performance_split_actionability_rows),
                        _split_summary_card("Snapshot Modes", AppState.performance_split_tracking_mode_rows),
                        columns=rx.breakpoints(initial="1", xl="3"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Snapshot Batches",
                        "Review each saved slate in its original snapshot group, including the note captured at save time.",
                        "Snapshot History",
                    ),
                    rx.cond(
                        AppState.performance_snapshot_groups.length() == 0,
                        intentional_empty_state(
                            "No saved snapshot groups are available yet.",
                            "Save a board snapshot to start building grouped performance history.",
                        ),
                        rx.vstack(
                            rx.foreach(AppState.performance_snapshot_groups, _snapshot_group_card),
                            spacing="3",
                            width="100%",
                        ),
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Delete Tracked Rows",
                        "Remove individual tracked bets from the current filtered view.",
                        "Cleanup",
                    ),
                    rx.cond(
                        AppState.filtered_performance_rows.length() == 0,
                        intentional_empty_state(
                            "No tracked rows are visible to delete.",
                            "Adjust the Performance filters if you want to remove a specific saved row.",
                        ),
                        rx.vstack(
                            rx.foreach(AppState.filtered_performance_rows, _performance_delete_row),
                            spacing="2",
                            width="100%",
                        ),
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            background=COLORS["light_canvas"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="28px",
            padding=rx.breakpoints(initial="1rem", md="1.2rem", xl="1.35rem"),
            box_shadow="0 12px 32px rgba(15, 23, 42, 0.08)",
        ),
        light=True,
    )
