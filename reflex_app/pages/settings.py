from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import dashboard_section_header, dashboard_surface_card
from reflex_app.components.shell import page_shell
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS


def _about_metric_card(label: str, value, helper: str) -> rx.Component:
    return dashboard_surface_card(
        rx.text(
            label,
            font_size="0.72rem",
            letter_spacing="0.14em",
            text_transform="uppercase",
            color=COLORS["light_muted_2"],
            font_weight="700",
        ),
        rx.text(value, font_size="1.9rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.03em"),
        rx.text(helper, font_size="0.82rem", color=COLORS["light_muted"], line_height="1.45"),
        style={
            "min_height": "152px",
            "justify_content": "space-between",
            "background": "linear-gradient(180deg, #ffffff 0%, #f9fbfe 100%)",
            "border": f"1px solid {COLORS['light_border']}",
            "box_shadow": "0 10px 24px rgba(15, 23, 42, 0.05)",
        },
    )


def _about_info_card(eyebrow: str, title: str, copy: str, items: list[tuple[str, str]]) -> rx.Component:
    return dashboard_surface_card(
        dashboard_section_header(title, copy, eyebrow),
        rx.vstack(
            *[
                rx.box(
                    rx.vstack(
                        rx.text(item_title, font_size="0.82rem", font_weight="800", color=COLORS["light_text"]),
                        rx.text(item_copy, font_size="0.78rem", color=COLORS["light_muted"], line_height="1.45"),
                        spacing="1",
                        align="start",
                        width="100%",
                    ),
                    width="100%",
                    padding="0.78rem 0.82rem",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="16px",
                )
                for item_title, item_copy in items
            ],
            spacing="3",
            width="100%",
        ),
        style={
            "padding": "1rem",
            "background": "linear-gradient(180deg, #ffffff 0%, #f8fafd 100%)",
            "border": f"1px solid {COLORS['light_border']}",
            "box_shadow": "0 8px 20px rgba(15, 23, 42, 0.04)",
        },
    )


def settings_page() -> rx.Component:
    return page_shell(
        "Settings / About",
        "Product-facing guidance for how the model works, what powers the numbers, and how to use the board with confidence.",
        rx.box(
            rx.vstack(
                dashboard_surface_card(
                    rx.vstack(
                        rx.text(
                            "About the Model",
                            font_size="0.74rem",
                            letter_spacing="0.14em",
                            text_transform="uppercase",
                            color=COLORS["light_muted_2"],
                            font_weight="800",
                        ),
                        rx.text(
                            "A probability-first MLB betting model built to turn simulations, market pricing, and game context into clearer betting opportunities.",
                            font_size="1.2rem",
                            font_weight="900",
                            color=COLORS["light_text"],
                            letter_spacing="-0.03em",
                            line_height="1.2",
                        ),
                        rx.text(
                            "The model estimates win probability first, then compares those probabilities to sportsbook prices so edges are explained in a way that is easier to trust and easier to act on.",
                            font_size="0.9rem",
                            color=COLORS["light_muted"],
                            line_height="1.55",
                            max_width="860px",
                        ),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    style={
                        "padding": "1.15rem 1.15rem 1.08rem",
                        "background": "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                        "border": f"1px solid {COLORS['light_border']}",
                        "box_shadow": "0 12px 30px rgba(15, 23, 42, 0.05)",
                    },
                ),
                dashboard_surface_card(
                    dashboard_section_header(
                        "Model Configuration",
                        "The most important runtime settings, presented as product-level signals instead of technical internals.",
                        "Configuration",
                    ),
                    rx.grid(
                        _about_metric_card(
                            "Simulation Count",
                            AppState.model_simulation_count,
                            "Monte Carlo runs per game used to stabilize the probability output.",
                        ),
                        _about_metric_card(
                            "Run Environment",
                            AppState.model_run_dispersion,
                            "Dispersion control for how tightly or loosely scoring spreads around the baseline run environment.",
                        ),
                        _about_metric_card(
                            "Database Status",
                            AppState.model_database_status,
                            "Confirms whether the app can read saved game, projection, and prediction data.",
                        ),
                        columns=rx.breakpoints(initial="1", md="3"),
                        spacing="4",
                        width="100%",
                    ),
                ),
                rx.grid(
                    _about_info_card(
                        "Core Components",
                        "Model Components",
                        "The board blends a few focused systems rather than one opaque black box.",
                        [
                            ("Game Simulation Engine", "Runs repeated game simulations to estimate true win probability and expected scoring ranges."),
                            ("Lineup Strength Model", "Translates lineup quality into team-level offensive adjustments before simulation."),
                            ("Pitching Model", "Uses starter quality and bullpen context to shape run prevention expectations."),
                            ("Probability Engine", "Converts model output and market prices into implied probabilities, no-vig views, edge, and EV."),
                            ("Season Monitoring", "Tracks projected wins, standings context, and playoff shape to support longer-horizon reads."),
                        ],
                    ),
                    _about_info_card(
                        "Usage Guide",
                        "How to Use the App",
                        "A quick guide to reading the signals without getting lost in the UI.",
                        [
                            ("Model Lean", "The side or total the model prefers after comparing projected outcomes to market price."),
                            ("Edge / EV", "Edge compares model probability to no-vig market probability, while EV estimates whether the price is worth betting."),
                            ("Best Bet Signals", "Best Bet labels surface the strongest combinations of edge and expected value on the board."),
                            ("Dashboard vs Daily Matchups", "Dashboard is the fast summary view; Daily Matchups is the deeper game-by-game workspace."),
                        ],
                    ),
                    columns=rx.breakpoints(initial="1", xl="2"),
                    spacing="4",
                    width="100%",
                ),
                _about_info_card(
                    "Inputs & Assumptions",
                    "Data & Assumptions",
                    "The model is only as useful as the assumptions behind it, so the board keeps those visible and easy to understand.",
                    [
                        ("Lineup Inputs", "Projected lineups influence offensive strength and help the model react to missing or upgraded bats."),
                        ("Pitcher Ratings", "Starter quality and available pitcher signals feed the expected run environment on both sides."),
                        ("Park and Weather Adjustments", "Ballpark factors plus weather context help translate neutral talent into game-specific scoring conditions."),
                        ("Simulation Approach", "The app uses repeated game simulation to estimate probabilities instead of relying on a single deterministic score."),
                    ],
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
            background=COLORS["light_canvas"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="28px",
            padding=rx.breakpoints(initial="1rem", md="1.2rem", xl="1.3rem"),
            box_shadow="0 12px 30px rgba(15, 23, 42, 0.05)",
        ),
        light=True,
    )
