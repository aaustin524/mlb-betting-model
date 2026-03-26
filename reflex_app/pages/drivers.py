from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import (
    dashboard_compact_list_card,
    dashboard_model_mover_card,
    dashboard_pitcher_card,
    dashboard_section_header,
    dashboard_signal_card,
    dashboard_surface_card,
)
from reflex_app.components.shell import page_shell
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def drivers_page() -> rx.Component:
    return page_shell(
        "Drivers / Model Factors",
        "A lighter, cleaner factor view for starters, lineups, bullpens, and broader team-shape signals behind the board.",
        rx.box(
            rx.vstack(
                dashboard_surface_card(
                    dashboard_section_header("Top Drivers Today", "A quick read on the clearest starter, lineup, bullpen, and team-profile signals behind the slate.", "Primary Focus"),
                    rx.grid(
                        rx.foreach(
                            AppState.driver_top_signal_cards,
                            lambda card: dashboard_signal_card(
                                card["label"],
                                card["value"],
                                card["stat"],
                                card["note"],
                            ),
                        ),
                        columns=rx.breakpoints(initial="1", md="2"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Today's Starting Pitchers",
                        "Top 5 slate-shaping arms, shown as compact ranked cards.",
                        "Pitching Focus",
                    ),
                    rx.vstack(
                        rx.foreach(AppState.driver_today_pitcher_cards, dashboard_pitcher_card),
                        spacing="3",
                        width="100%",
                    ),
                ),
                rx.grid(
                    dashboard_compact_list_card(
                        "Pitcher Watch",
                        "Supporting Detail",
                        "Reduced to the top 8 reference arms with lighter visual weight.",
                        AppState.driver_pitcher_watch_rows,
                    ),
                    dashboard_compact_list_card(
                        "Lineup Strength",
                        "Supporting Detail",
                        "Top 8 lineups, reformatted as a lighter ranked list.",
                        AppState.driver_lineup_rows,
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Bullpen Signals",
                        "Best and most vulnerable relief groups, merged into one cleaner read.",
                        "Relief Focus",
                    ),
                    rx.grid(
                        dashboard_compact_list_card(
                            "Best Bullpens",
                            "Left Panel",
                            "Top 5 relief units by bullpen score and stability.",
                            AppState.driver_best_bullpen_rows,
                        ),
                        dashboard_compact_list_card(
                            "At-Risk Bullpens",
                            "Right Panel",
                            "Top 5 bullpens carrying the most current stress.",
                            AppState.driver_risky_bullpen_rows,
                        ),
                        columns=rx.breakpoints(initial="1", xl="2"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Model Movers",
                        "Top 8 teams, reframed as compact identity entries with lighter support metrics.",
                        "Team Identity",
                    ),
                    rx.vstack(
                        rx.foreach(AppState.driver_model_mover_cards, dashboard_model_mover_card),
                        spacing="3",
                        width="100%",
                    ),
                ),
                spacing="5",
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
