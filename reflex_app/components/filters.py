from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import dashboard_section_header, dashboard_surface_card, section_header, surface_card
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS, CONTROL_STYLE, SECTION_TITLE_STYLE


def _control_stack(label: str, control: rx.Component, helper: str, light: bool = False) -> rx.Component:
    return rx.vstack(
        rx.text(
            label,
            style=SECTION_TITLE_STYLE if not light else {
                "font_size": "0.72rem",
                "letter_spacing": "0.15em",
                "text_transform": "uppercase",
                "color": COLORS["light_muted_2"],
                "font_weight": "700",
            },
        ),
        control,
        rx.text(helper, color=COLORS["muted_2"] if not light else COLORS["light_muted_2"], font_size="0.77rem"),
        spacing="1",
        align="start",
        width="100%",
    )


def filter_bar(light: bool = False) -> rx.Component:
    card_component = dashboard_surface_card if light else surface_card
    header_component = dashboard_section_header if light else section_header
    control_style = dict(CONTROL_STYLE)
    if light:
        control_style.update(
            {
                "background": COLORS["light_panel"],
                "border": f"1px solid {COLORS['light_border_strong']}",
                "color": COLORS["light_text"],
                "_focus": {
                    "border": f"1px solid {COLORS['light_accent']}",
                    "box_shadow": "0 0 0 3px rgba(37, 99, 235, 0.10)",
                },
            }
        )

    metric_box_style = {
        "padding": "0.68rem 0.82rem",
        "border_radius": "14px",
        "min_width": "160px",
        "background": COLORS["panel_soft"] if not light else COLORS["light_panel_alt"],
        "border": f"1px solid {COLORS['border']}" if not light else f"1px solid {COLORS['light_border']}",
    }

    return card_component(
        rx.hstack(
            header_component("Board Filters", "Tight controls for quickly narrowing the slate without losing context.", "Controls"),
            rx.spacer(),
            rx.vstack(
                rx.hstack(
                    rx.button(
                        rx.cond(AppState.odds_status_collapsed, "Show Odds Info", "Hide Odds Info"),
                        on_click=AppState.toggle_odds_status_collapsed,
                        background=COLORS["panel"] if not light else COLORS["light_panel"],
                        color=COLORS["text"] if not light else COLORS["light_text"],
                        border=f"1px solid {COLORS['border_strong']}" if not light else f"1px solid {COLORS['light_border_strong']}",
                        border_radius="12px",
                        padding="0.62rem 0.92rem",
                        font_weight="700",
                        box_shadow="none",
                        _hover={"background": COLORS["panel_alt"] if not light else COLORS["light_panel_alt"]},
                    ),
                    rx.button(
                        "Refresh Data",
                        on_click=AppState.refresh,
                        background=COLORS["panel"] if not light else COLORS["light_panel"],
                        color=COLORS["text"] if not light else COLORS["light_text"],
                        border=f"1px solid {COLORS['border_strong']}" if not light else f"1px solid {COLORS['light_border_strong']}",
                        border_radius="12px",
                        padding="0.62rem 0.92rem",
                        font_weight="700",
                        box_shadow="none",
                        _hover={"background": COLORS["panel_alt"] if not light else COLORS["light_panel_alt"]},
                    ),
                    spacing="2",
                    justify="end",
                    width="100%",
                ),
                rx.cond(
                    AppState.odds_status_collapsed,
                    rx.fragment(),
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Odds Source:",
                                font_size="0.76rem",
                                font_weight="700",
                                color=COLORS["text"] if not light else COLORS["light_text"],
                            ),
                            rx.text(
                                AppState.odds_source_label,
                                font_size="0.76rem",
                                font_weight="700",
                                color=COLORS["text"] if not light else COLORS["light_text"],
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.hstack(
                            rx.text(
                                "Last refresh:",
                                font_size="0.75rem",
                                color=COLORS["muted_2"] if not light else COLORS["light_muted_2"],
                            ),
                            rx.text(
                                AppState.odds_last_refreshed_label,
                                font_size="0.75rem",
                                color=COLORS["muted_2"] if not light else COLORS["light_muted_2"],
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            AppState.odds_quota_label,
                            font_size="0.74rem",
                            color=COLORS["muted_2"] if not light else COLORS["light_muted_2"],
                        ),
                        rx.text(
                            AppState.odds_refresh_note,
                            font_size="0.74rem",
                            color=COLORS["muted_2"] if not light else COLORS["light_muted_2"],
                            max_width="420px",
                            line_height="1.45",
                        ),
                        spacing="1",
                        align="end",
                    ),
                ),
                spacing="2",
                align="end",
            ),
            width="100%",
            align="start",
            spacing="3",
            flex_wrap="wrap",
        ),
        rx.hstack(
            rx.box(
                rx.text(
                    "Filtered Games",
                    style=SECTION_TITLE_STYLE if not light else {
                        "font_size": "0.72rem",
                        "letter_spacing": "0.15em",
                        "text_transform": "uppercase",
                        "color": COLORS["light_muted_2"],
                        "font_weight": "700",
                    },
                ),
                rx.text(
                    AppState.filtered_matchups.length(),
                    font_size="1.2rem",
                    font_weight="800",
                    color=COLORS["text"] if not light else COLORS["light_text"],
                ),
                **metric_box_style,
            ),
            rx.box(
                rx.text(
                    "Visible Cards",
                    style=SECTION_TITLE_STYLE if not light else {
                        "font_size": "0.72rem",
                        "letter_spacing": "0.15em",
                        "text_transform": "uppercase",
                        "color": COLORS["light_muted_2"],
                        "font_weight": "700",
                    },
                ),
                rx.text(
                    AppState.filtered_matchup_cards.length(),
                    font_size="1.2rem",
                    font_weight="800",
                    color=COLORS["text"] if not light else COLORS["light_text"],
                ),
                **metric_box_style,
            ),
            spacing="3",
            flex_wrap="wrap",
            width="100%",
        ),
        rx.grid(
            _control_stack(
                "Team",
                rx.select(
                    AppState.team_options,
                    value=AppState.selected_team,
                    on_change=AppState.set_selected_team,
                    width="100%",
                    variant="surface",
                    **control_style,
                ),
                "Show games where that team appears.",
                light=light,
            ),
            _control_stack(
                "Signal",
                rx.select(
                    AppState.signal_options,
                    value=AppState.selected_signal,
                    on_change=AppState.set_selected_signal,
                    width="100%",
                    variant="surface",
                    **control_style,
                ),
                "Filter for strong, lean, or full-board views.",
                light=light,
            ),
            columns=rx.breakpoints(initial="1", md="2"),
            spacing="3",
            width="100%",
        ),
    )
