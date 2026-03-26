from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import (
    dashboard_section_header,
    dashboard_surface_card,
    daily_matchup_board_card,
    intentional_empty_state,
    top_bet_empty_state,
    top_bet_hero_card,
)
from reflex_app.components.filters import filter_bar
from reflex_app.components.shell import page_shell
from reflex_app.components.tables import light_table
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def daily_matchups_page() -> rx.Component:
    return page_shell(
        "Daily Matchups",
        "Fast board view for scanning the strongest game signals first, then opening the full matchup data only when needed.",
        rx.box(
            rx.vstack(
                filter_bar(light=True),
                rx.cond(
                    AppState.has_top_bet_of_day,
                    top_bet_hero_card(AppState.top_bet_of_day),
                    top_bet_empty_state(),
                ),
                dashboard_surface_card(
                    rx.hstack(
                        dashboard_section_header(
                            "Slate Board",
                            "Each card surfaces signal strength, fair win pricing, projected total, and model lean in one quick pass.",
                            "Decision View",
                        ),
                        rx.spacer(),
                        rx.select(
                            AppState.snapshot_tracking_mode_options,
                            value=AppState.selected_snapshot_tracking_mode,
                            on_change=AppState.set_selected_snapshot_tracking_mode,
                            width=rx.breakpoints(initial="100%", sm="220px"),
                            variant="surface",
                            background=COLORS["light_panel"],
                            border=f"1px solid {COLORS['light_border_strong']}",
                            color=COLORS["light_text"],
                        ),
                        rx.input(
                            value=AppState.snapshot_note_input,
                            on_change=AppState.set_snapshot_note_input,
                            placeholder="Optional snapshot note",
                            width=rx.breakpoints(initial="100%", sm="240px"),
                            background=COLORS["light_panel"],
                            border=f"1px solid {COLORS['light_border_strong']}",
                            color=COLORS["light_text"],
                            border_radius="12px",
                        ),
                        rx.button(
                            "Save Board Snapshot",
                            on_click=AppState.lock_snapshot,
                            background=COLORS["light_panel"],
                            color=COLORS["light_text"],
                            border=f"1px solid {COLORS['light_border_strong']}",
                            border_radius="12px",
                            padding="0.72rem 0.95rem",
                            font_weight="700",
                            _hover={"background": COLORS["light_panel_alt"]},
                            white_space="nowrap",
                        ),
                        rx.button(
                            rx.cond(AppState.show_full_matchup_table, "Hide Full Data", "Show Full Data"),
                            on_click=AppState.toggle_show_full_matchup_table,
                            background=COLORS["light_panel"],
                            color=COLORS["light_text"],
                            border=f"1px solid {COLORS['light_border_strong']}",
                            border_radius="12px",
                            padding="0.72rem 0.95rem",
                            font_weight="700",
                            _hover={"background": COLORS["light_panel_alt"]},
                            white_space="nowrap",
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
                            padding="0.82rem 0.88rem",
                            background=COLORS["light_panel_alt"],
                            border=f"1px solid {COLORS['light_border']}",
                            border_radius="16px",
                        ),
                    ),
                    rx.cond(
                        AppState.daily_matchup_decision_cards.length() == 0,
                        intentional_empty_state(
                            "No games match the current filter set.",
                            "Reset the board filters or refresh slate data to bring matchups back into view.",
                        ),
                        rx.grid(
                            rx.foreach(AppState.daily_matchup_decision_cards, daily_matchup_board_card),
                            columns=rx.breakpoints(initial="1", lg="2"),
                            spacing="4",
                            width="100%",
                        ),
                    ),
                ),
                rx.cond(
                    AppState.show_full_matchup_table,
                    light_table(
                        "Full Matchup Data",
                        AppState.filtered_matchups,
                        AppState.matchup_columns,
                        "Supporting board detail only. Use the cards above first, then open this table for validation and deeper inspection.",
                    ),
                    rx.fragment(),
                ),
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
