from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import (
    dashboard_kpi_card,
    compact_watch_matchup,
    dashboard_play_card,
    dashboard_section_header,
    dashboard_surface_card,
    decision_banner,
    intentional_empty_state,
    market_status_card,
    primary_lean_card,
)
from reflex_app.components.shell import page_shell
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def dashboard_page() -> rx.Component:
    return page_shell(
        "Dashboard",
        "Decision-first board view with the clearest opportunities, strongest model leans, and featured slate context.",
        rx.box(
            rx.vstack(
                rx.grid(
                    decision_banner(
                        "Board Status",
                        AppState.hero_games_value,
                        "Start here. Read the current slate size, then move immediately into opportunities or model leans below.",
                        "accent",
                    ),
                    decision_banner(
                        "Best EV",
                        AppState.hero_best_ev_value,
                        "When no positive EV spots are available, the Dashboard shifts focus toward model-only leans and featured matchups.",
                        "success",
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
                ),
                rx.grid(
                    rx.foreach(
                        AppState.summary_cards,
                        lambda card: dashboard_kpi_card(card["label"], card["value"], card["delta"]),
                    ),
                    columns=rx.breakpoints(initial="1", sm="2", lg="4"),
                    spacing="4",
                    width="100%",
                ),
                rx.grid(
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Top Leans",
                            "Model-only conviction picks ranked by edge, with the key drivers attached directly to each lean.",
                            "Primary Focus",
                        ),
                        rx.cond(
                            AppState.top_lean_driver_groups.length() == 0,
                            intentional_empty_state(
                                "No model leans are available yet.",
                                "Refresh after the slate loads to populate this panel with the strongest favorite and split signals.",
                            ),
                            rx.grid(
                                rx.foreach(AppState.top_lean_driver_groups, primary_lean_card),
                                columns=rx.breakpoints(initial="1", xl="2"),
                                spacing="4",
                                width="100%",
                            ),
                        ),
                    ),
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Action Board",
                            "Positive-EV opportunities stay here. When none are active, this panel becomes a market-status cue instead of dead space.",
                            "Secondary",
                        ),
                        rx.cond(
                            AppState.top_plays.length() == 0,
                            market_status_card(),
                            rx.grid(
                                rx.foreach(AppState.top_plays, dashboard_play_card),
                                columns=rx.breakpoints(initial="1", xl="2"),
                                spacing="4",
                                width="100%",
                            ),
                        ),
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
                ),
                rx.grid(
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Board Drivers",
                            "A lighter watchlist of market-shaping signals that are not already embedded into the top-lean cards above.",
                            "Tertiary",
                        ),
                        rx.cond(
                            AppState.today_impact_cards.length() == 0,
                            intentional_empty_state(
                                "No drivers are available yet.",
                                "Driver context will appear here as soon as the board services return starter, lineup, and bullpen signals.",
                            ),
                            rx.vstack(
                                rx.foreach(
                                    AppState.today_impact_cards,
                                    lambda item: rx.hstack(
                                        rx.box(width="8px", height="8px", border_radius="999px", background=COLORS["light_accent"], margin_top="0.32rem"),
                                        rx.vstack(
                                            rx.text(item["label"], font_size="0.84rem", font_weight="700", color=COLORS["light_text"]),
                                            rx.text(f"{item['team']} | {item['value']}", font_size="0.82rem", color=COLORS["light_muted"], line_height="1.4"),
                                            spacing="1",
                                            align="start",
                                        ),
                                        width="100%",
                                        align="start",
                                        spacing="2",
                                    ),
                                ),
                                spacing="3",
                                width="100%",
                            ),
                        ),
                    ),
                    dashboard_surface_card(
                        dashboard_section_header(
                            "Watchlist Matchups",
                            "A reduced slate summary kept intentionally lighter than the Daily Matchups page.",
                            "Tertiary",
                        ),
                        rx.cond(
                            AppState.featured_matchup_cards.length() == 0,
                            intentional_empty_state(
                                "No watchlist games are ready yet.",
                                "Featured board rows will appear here once the slate loads.",
                            ),
                            rx.vstack(
                                rx.foreach(AppState.featured_matchup_cards, compact_watch_matchup),
                                spacing="3",
                                width="100%",
                            ),
                        ),
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
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
