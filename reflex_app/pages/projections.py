from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import (
    dashboard_section_header,
    dashboard_signal_card,
    dashboard_surface_card,
    outlook_support_card,
    projection_tier_card,
)
from reflex_app.components.shell import page_shell
from reflex_app.components.tables import light_table
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def projections_page() -> rx.Component:
    return page_shell(
        "Season Projections",
        "Presentation-ready standings, playoff odds, and saved prediction snapshots from the existing season monitor services.",
        rx.box(
            rx.vstack(
                dashboard_surface_card(
                    dashboard_section_header(
                        "Season Outlook",
                        "Fast-read season board for projected leaders, best profiles, and the teams shaping the long-range picture.",
                        "Outlook Board",
                    ),
                    rx.grid(
                        rx.foreach(
                            AppState.projection_hero_cards,
                            lambda card: dashboard_signal_card(
                                card["label"],
                                card["value"],
                                card["stat"],
                                card["note"],
                                card["helper"],
                                card["emphasis"],
                                card["context"],
                            ),
                        ),
                        columns=rx.breakpoints(initial="1", md="2", xl="4"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Team Tiers",
                        "Grouped into outlook buckets using fixed rank bands so the board stays easy to scan.",
                        "Tier View",
                    ),
                    rx.grid(
                        projection_tier_card("Elite Contenders", AppState.elite_projection_rows),
                        projection_tier_card("Playoff Teams", AppState.playoff_projection_rows),
                        projection_tier_card("Fringe Teams", AppState.fringe_projection_rows),
                        projection_tier_card("Rebuilding", AppState.rebuilding_projection_rows),
                        columns=rx.breakpoints(initial="1", xl="2"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                light_table(
                    "Projected Standings",
                    AppState.projected_standings_view,
                    ["Rank", "Team", "Wins", "Win %"],
                    "Top-10 projection board designed for a quick executive read instead of a dense spreadsheet.",
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Division Standings",
                        "Traditional division tables with each club's current record and projected finish side by side.",
                        "Current + Projected",
                    ),
                    rx.grid(
                        light_table(
                            "AL East",
                            AppState.al_east_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        light_table(
                            "AL Central",
                            AppState.al_central_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        light_table(
                            "AL West",
                            AppState.al_west_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        light_table(
                            "NL East",
                            AppState.nl_east_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        light_table(
                            "NL Central",
                            AppState.nl_central_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        light_table(
                            "NL West",
                            AppState.nl_west_standings_rows,
                            ["Team", "Current", "Projected", "Current Win %", "Projected Win %", "Outlook"],
                            "Current record and projected finish for the full division.",
                        ),
                        columns=rx.breakpoints(initial="1", xl="2"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                outlook_support_card(
                    "Playoff Odds",
                    "Compact playoff probability snapshot designed to become the quick-read odds panel.",
                    AppState.playoff_outlook_rows,
                ),
                outlook_support_card(
                    "Latest Saved Predictions",
                    "Small product-facing preview for stored model outputs and recent saved board signals.",
                    AppState.prediction_outlook_rows,
                ),
                light_table(
                    "Upcoming Predictions With Market Compare",
                    AppState.upcoming_prediction_table_rows,
                    [
                        "Date",
                        "Matchup",
                        "Away Win %",
                        "Home Win %",
                        "Away Market %",
                        "Home Market %",
                        "Away Edge",
                        "Home Edge",
                        "Recommended",
                        "Bet",
                    ],
                    "Direct verification table for upcoming games where model probabilities, no-vig market probabilities, edges, and bet flags can be checked in one place.",
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
