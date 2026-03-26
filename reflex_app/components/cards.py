from __future__ import annotations

import reflex as rx

from reflex_app.state.app_state import AppState
from reflex_app.styles import (
    CARD_STYLE,
    COLORS,
    SECTION_SUBTITLE_STYLE,
    SECTION_TITLE_STYLE,
    SOFT_CARD_STYLE,
)


def surface_card(*children: rx.Component, style: dict | None = None) -> rx.Component:
    card_style = dict(CARD_STYLE)
    if style:
        card_style.update(style)
    return rx.box(
        rx.vstack(*children, spacing="3", align="start", width="100%"),
        style=card_style,
        width="100%",
    )


def soft_card(*children: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(*children, spacing="2", align="start", width="100%"),
        style=SOFT_CARD_STYLE,
        width="100%",
    )


def _metric_chip(label: str, value: str, tone: str = "neutral") -> rx.Component:
    tone_map = {
        "neutral": COLORS["panel_soft"],
        "accent": COLORS["accent_soft"],
        "success": COLORS["success_soft"],
        "info": COLORS["info_soft"],
    }
    return rx.box(
        rx.vstack(
            rx.text(label, color=COLORS["muted_2"], font_size="0.66rem", text_transform="uppercase", letter_spacing="0.12em"),
            rx.text(value, font_weight="700", font_size="0.92rem", color=COLORS["text"]),
            spacing="1",
            align="start",
        ),
        padding="0.72rem 0.8rem",
        background=tone_map.get(tone, COLORS["panel_soft"]),
        border=f"1px solid {COLORS['border']}",
        border_radius="14px",
        width="100%",
    )


def _signal_badge(label) -> rx.Component:
    return rx.box(
        label,
        padding="0.36rem 0.66rem",
        border_radius="999px",
        font_size="0.75rem",
        font_weight="700",
        background=rx.cond(
            label == "Strong Bet",
            COLORS["success_soft"],
            rx.cond(label == "Lean", COLORS["accent_soft"], COLORS["panel_soft"]),
        ),
        border=rx.cond(
            label == "Strong Bet",
            f"1px solid {COLORS['success']}",
            rx.cond(label == "Lean", f"1px solid {COLORS['accent']}", f"1px solid {COLORS['border']}"),
        ),
        color=rx.cond(
            label == "Strong Bet",
            COLORS["success"],
            rx.cond(label == "Lean", COLORS["accent"], COLORS["muted"]),
        ),
    )


def section_header(title: str, helper: str | None = None, eyebrow: str | None = None) -> rx.Component:
    return rx.vstack(
        rx.cond(
            eyebrow is None,
            rx.fragment(),
            rx.text(eyebrow, style=SECTION_TITLE_STYLE),
        ),
        rx.hstack(
            rx.vstack(
                rx.heading(title, size="5", color=COLORS["text"]),
                rx.cond(
                    helper is None,
                    rx.fragment(),
                    rx.text(helper, style=SECTION_SUBTITLE_STYLE, max_width="720px"),
                ),
                spacing="1",
                align="start",
            ),
            width="100%",
            align="start",
        ),
        spacing="1",
        align="start",
        width="100%",
    )


def stat_card(label: str, value: str, delta: str) -> rx.Component:
    return surface_card(
        rx.hstack(
            rx.text(label, style=SECTION_TITLE_STYLE),
            rx.spacer(),
            rx.box(width="10px", height="10px", border_radius="999px", background=COLORS["accent"]),
            width="100%",
            align="center",
        ),
        rx.heading(value, size="8", line_height="1", color=COLORS["text"]),
        rx.text(delta, color=COLORS["muted"], font_size="0.84rem", line_height="1.4"),
        style={
            "min_height": "134px",
            "background": "linear-gradient(180deg, rgba(16,32,51,0.98) 0%, rgba(12,27,44,0.98) 100%)",
        },
    )


def hero_summary_card(
    title: str,
    subtitle: str,
    accent_label: str,
    accent_value: str,
    helper: str,
) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    accent_label,
                    padding="0.22rem 0.5rem",
                    border_radius="999px",
                    background=COLORS["accent_soft"],
                    border=f"1px solid {COLORS['accent']}",
                    color=COLORS["accent"],
                    font_size="0.68rem",
                    font_weight="700",
                ),
                rx.spacer(),
                rx.text(accent_value, color=COLORS["text"], font_weight="800", font_size="1.35rem"),
                width="100%",
                align="center",
            ),
            rx.heading(title, size="7", color=COLORS["text"]),
            rx.text(subtitle, color=COLORS["muted"], font_size="0.9rem", line_height="1.45", max_width="560px"),
            rx.text(helper, color=COLORS["muted_2"], font_size="0.78rem"),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        padding=rx.breakpoints(initial="1rem", md="1.15rem"),
        border_radius="20px",
        background="linear-gradient(135deg, rgba(18,38,61,0.98) 0%, rgba(9,22,38,0.98) 60%, rgba(30,120,255,0.20) 100%)",
        border=f"1px solid {COLORS['border_strong']}",
        box_shadow="0 18px 42px rgba(2, 8, 23, 0.30)",
    )


def play_card(play: dict[str, str]) -> rx.Component:
    return surface_card(
        rx.hstack(
            rx.vstack(
                rx.text(play["bet_type"], style=SECTION_TITLE_STYLE),
                rx.text(play["pick"], font_weight="800", font_size="1.08rem", color=COLORS["text"]),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            _signal_badge(play["flag"]),
            width="100%",
            align="start",
        ),
        rx.text(play["matchup"], font_size="0.92rem", color=COLORS["text"]),
        rx.grid(
            _metric_chip("Edge", play["edge"], "accent"),
            _metric_chip("EV", play["ev"], "success"),
            _metric_chip("Line", play["line"], "info"),
            columns=rx.breakpoints(initial="1", sm="3"),
            spacing="3",
            width="100%",
        ),
        style={"padding": "1.05rem"},
    )


def insight_card(item: dict[str, str]) -> rx.Component:
    return surface_card(
        rx.text(item["label"], style=SECTION_TITLE_STYLE),
        rx.text(item["team"], font_weight="800", font_size="1rem", color=COLORS["text"]),
        rx.text(item["value"], color=COLORS["muted"], font_size="0.84rem", line_height="1.4"),
        style={"min_height": "122px"},
    )


def matchup_card(card: dict[str, str]) -> rx.Component:
    away_win = f"{card['away_win']}%"
    home_win = f"{card['home_win']}%"
    return surface_card(
        rx.hstack(
            rx.vstack(
                rx.text(card["matchup"], font_weight="800", font_size="1rem", color=COLORS["text"]),
                rx.text(
                    f"{card['away_pitcher']} vs {card['home_pitcher']}",
                    color=COLORS["muted"],
                    font_size="0.81rem",
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            _signal_badge(card["bet_flag"]),
            width="100%",
            align="start",
        ),
        rx.box(
            rx.hstack(
                rx.box(
                    width=f"{card['away_win']}%",
                    min_width="12%",
                    height="8px",
                    border_radius="999px",
                    background=card["away_primary"],
                    box_shadow=f"0 0 18px {card['away_primary']}55",
                ),
                rx.box(
                    width=f"{card['home_win']}%",
                    min_width="12%",
                    height="8px",
                    border_radius="999px",
                    background=card["home_primary"],
                    box_shadow=f"0 0 18px {card['home_primary']}55",
                ),
                spacing="2",
                width="100%",
                align="center",
            ),
            width="100%",
            padding="0.15rem 0 0.05rem 0",
        ),
        rx.grid(
            rx.box(
                rx.hstack(
                    rx.box(
                        rx.image(src=card["away_logo"], alt=card["away_team"], width="44px", height="44px", object_fit="contain"),
                        width="52px",
                        height="52px",
                        border_radius="14px",
                        background=f"linear-gradient(180deg, {card['away_primary']}22 0%, rgba(255,255,255,0.04) 100%)",
                        border=f"1px solid {COLORS['border']}",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.hstack(
                            rx.text(card["away_abbr"], style=SECTION_TITLE_STYLE),
                            rx.cond(
                                card["favorite"] == card["away_team"],
                                rx.box(
                                    "Fav",
                                    padding="0.16rem 0.45rem",
                                    border_radius="999px",
                                    background=COLORS["accent_soft"],
                                    border=f"1px solid {COLORS['accent']}",
                                    color=COLORS["accent"],
                                    font_size="0.68rem",
                                    font_weight="700",
                                ),
                                rx.fragment(),
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(card["away_team"], font_weight="700", font_size="0.95rem", color=COLORS["text"]),
                        rx.heading(away_win, size="6", color=COLORS["text"]),
                        spacing="1",
                        align="start",
                    ),
                    width="100%",
                    align="center",
                    spacing="3",
                ),
                padding="0.9rem",
                border_radius="16px",
                background=f"linear-gradient(180deg, {card['away_primary']}18 0%, rgba(16,32,51,0.96) 100%)",
                border=f"1px solid {COLORS['border']}",
            ),
            rx.box(
                rx.hstack(
                    rx.box(
                        rx.image(src=card["home_logo"], alt=card["home_team"], width="44px", height="44px", object_fit="contain"),
                        width="52px",
                        height="52px",
                        border_radius="14px",
                        background=f"linear-gradient(180deg, {card['home_primary']}22 0%, rgba(255,255,255,0.04) 100%)",
                        border=f"1px solid {COLORS['border']}",
                        display="flex",
                        align_items="center",
                        justify_content="center",
                        flex_shrink="0",
                    ),
                    rx.vstack(
                        rx.hstack(
                            rx.text(card["home_abbr"], style=SECTION_TITLE_STYLE),
                            rx.cond(
                                card["favorite"] == card["home_team"],
                                rx.box(
                                    "Fav",
                                    padding="0.16rem 0.45rem",
                                    border_radius="999px",
                                    background=COLORS["accent_soft"],
                                    border=f"1px solid {COLORS['accent']}",
                                    color=COLORS["accent"],
                                    font_size="0.68rem",
                                    font_weight="700",
                                ),
                                rx.fragment(),
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(card["home_team"], font_weight="700", font_size="0.95rem", color=COLORS["text"]),
                        rx.heading(home_win, size="6", color=COLORS["text"]),
                        spacing="1",
                        align="start",
                    ),
                    width="100%",
                    align="center",
                    spacing="3",
                ),
                padding="0.9rem",
                border_radius="16px",
                background=f"linear-gradient(180deg, {card['home_primary']}18 0%, rgba(16,32,51,0.96) 100%)",
                border=f"1px solid {COLORS['border']}",
            ),
            columns=rx.breakpoints(initial="1", sm="2"),
            spacing="3",
            width="100%",
        ),
        rx.grid(
            _metric_chip("Projected Score", card["projected_score"]),
            _metric_chip("Projected Total", card["projected_total"]),
            _metric_chip("Best Side", card["side_summary"]),
            _metric_chip("Market", card["market_summary"]),
            columns=rx.breakpoints(initial="1", md="2"),
            spacing="3",
            width="100%",
        ),
        style={"padding": "1.05rem"},
    )


def loading_panel() -> rx.Component:
    return surface_card(
        rx.center(
            rx.vstack(
                rx.spinner(size="3", color=COLORS["accent"]),
                rx.text("Loading board", font_weight="700", font_size="1rem", color=COLORS["text"]),
                rx.text(
                    "Collecting model outputs, ratings, and projections for the dashboard.",
                    color=COLORS["muted"],
                    font_size="0.86rem",
                ),
                spacing="3",
                align="center",
            ),
            min_height="260px",
            width="100%",
        )
    )


def empty_panel(title: str, helper: str) -> rx.Component:
    return surface_card(
        rx.text("No Data", style=SECTION_TITLE_STYLE),
        rx.text(title, font_weight="800", font_size="1rem", color=COLORS["text"]),
        rx.text(helper, color=COLORS["muted"], font_size="0.86rem", max_width="420px"),
    )


def dashboard_surface_card(*children: rx.Component, style: dict | None = None) -> rx.Component:
    card_style = {
        "background": COLORS["light_panel"],
        "border": "1px solid rgba(0,0,0,0.05)",
        "border_radius": "20px",
        "padding": "1rem",
        "box_shadow": "0 2px 6px rgba(0,0,0,0.04)",
    }
    if style:
        card_style.update(style)
    return rx.box(
        rx.vstack(*children, spacing="3", align="start", width="100%"),
        style=card_style,
        width="100%",
    )


def dashboard_section_header(title: str, helper: str | None = None, eyebrow: str | None = None) -> rx.Component:
    return rx.vstack(
        rx.cond(
            eyebrow is None,
            rx.fragment(),
            rx.text(
                eyebrow,
                font_size="0.7rem",
                letter_spacing="0.15em",
                text_transform="uppercase",
                color=COLORS["light_muted_2"],
                font_weight="800",
            ),
        ),
        rx.text(title, font_size="1.15rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.025em"),
        rx.cond(
            helper is None,
            rx.fragment(),
            rx.text(helper, font_size="0.84rem", color=COLORS["light_muted"], line_height="1.48", max_width="640px"),
        ),
        spacing="1",
        align="start",
        width="100%",
    )


def dashboard_kpi_card(label: str, value: str, delta: str) -> rx.Component:
    return dashboard_surface_card(
        rx.text(label, font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
        rx.hstack(
            rx.text(value, font_size="1.8rem", font_weight="800", color=COLORS["light_text"]),
            rx.spacer(),
            rx.box(width="10px", height="10px", border_radius="999px", background=COLORS["light_accent"]),
            width="100%",
            align="center",
        ),
        rx.text(delta, font_size="0.84rem", color=COLORS["light_muted"], line_height="1.4"),
        style={"min_height": "128px"},
    )


def _light_note_badge(label: str, tone: str = "secondary") -> rx.Component:
    background = rx.cond(
        tone == "primary",
        "linear-gradient(180deg, rgba(37, 99, 235, 0.12) 0%, rgba(37, 99, 235, 0.06) 100%)",
        COLORS["light_panel_alt"],
    )
    border = rx.cond(
        tone == "primary",
        "1px solid rgba(37, 99, 235, 0.22)",
        f"1px solid {COLORS['light_border']}",
    )
    color = rx.cond(
        tone == "primary",
        COLORS["light_accent"],
        COLORS["light_muted"],
    )
    return rx.box(
        label,
        padding="0.32rem 0.62rem",
        border_radius="999px",
        background=background,
        border=border,
        color=color,
        font_size="0.72rem",
        font_weight="800",
        white_space="nowrap",
        letter_spacing="0.01em",
    )


def dashboard_signal_card(
    label: str,
    value: str,
    stat: str,
    note: str,
    helper: str | None = None,
    emphasis: str = "secondary",
    context: str | None = None,
) -> rx.Component:
    min_height = rx.cond(emphasis == "primary", "212px", "172px")
    stat_size = rx.cond(emphasis == "primary", "2.7rem", "1.48rem")
    value_size = rx.cond(emphasis == "primary", "1.18rem", "1.03rem")
    title_color = rx.cond(emphasis == "primary", COLORS["light_text"], COLORS["light_text"])
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text(
                    label,
                    font_size="0.72rem",
                    letter_spacing="0.14em",
                    text_transform="uppercase",
                    color=COLORS["light_muted_2"],
                    font_weight="700",
                ),
                rx.cond(
                    context is None,
                    rx.fragment(),
                    rx.text(context, font_size="0.72rem", color=COLORS["light_muted"], font_weight="700"),
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            _light_note_badge(note, emphasis),
            width="100%",
            align="start",
            spacing="3",
        ),
        rx.vstack(
            rx.text(value, font_size=value_size, font_weight="800", color=title_color, line_height="1.2"),
            rx.text(stat, font_size=stat_size, font_weight="900", color=COLORS["light_text"], line_height="1.0", letter_spacing="-0.03em"),
            rx.cond(
                helper is None,
                rx.fragment(),
                rx.text(helper, font_size="0.82rem", color=COLORS["light_muted"], line_height="1.45", max_width="240px"),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        style={
            "min_height": min_height,
            "justify_content": "space-between",
            "padding": rx.cond(emphasis == "primary", "1.08rem 1.08rem 1.02rem", "1rem"),
            "background": rx.cond(
                emphasis == "primary",
                "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                "linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%)",
            ),
            "border": rx.cond(
                emphasis == "primary",
                "1px solid rgba(37, 99, 235, 0.16)",
                "1px solid rgba(15, 23, 42, 0.06)",
            ),
            "box_shadow": rx.cond(
                emphasis == "primary",
                "0 18px 40px rgba(15, 23, 42, 0.10)",
                "0 8px 20px rgba(15, 23, 42, 0.05)",
            ),
            "transition": "all 180ms ease",
            "_hover": {
                "transform": "translateY(-1px)",
                "box_shadow": rx.cond(
                    emphasis == "primary",
                    "0 20px 42px rgba(15, 23, 42, 0.11)",
                    "0 10px 22px rgba(15, 23, 42, 0.06)",
                ),
            },
        },
    )


def dashboard_rank_badge(value: str) -> rx.Component:
    return rx.box(
        value,
        width="42px",
        height="42px",
        display="flex",
        align_items="center",
        justify_content="center",
        border_radius="999px",
        background="rgba(0,0,0,0.04)",
        border=f"1px solid {COLORS['light_border_strong']}",
        color=COLORS["light_accent"],
        font_size="0.8rem",
        font_weight="800",
        flex_shrink="0",
        margin_right="0.1rem",
    )


def _volatility_badge(value: str) -> rx.Component:
    background = rx.cond(
        value == "Volatility: Low",
        "rgba(15, 159, 110, 0.10)",
        rx.cond(value == "Volatility: High", "rgba(244, 63, 94, 0.10)", COLORS["light_panel_alt"]),
    )
    border = rx.cond(
        value == "Volatility: Low",
        "1px solid rgba(15, 159, 110, 0.16)",
        rx.cond(value == "Volatility: High", "1px solid rgba(244, 63, 94, 0.16)", f"1px solid {COLORS['light_border']}"),
    )
    color = rx.cond(
        value == "Volatility: Low",
        COLORS["light_success"],
        rx.cond(value == "Volatility: High", COLORS["danger"], COLORS["light_text"]),
    )
    return rx.box(
        value,
        padding="0.32rem 0.58rem",
        border_radius="999px",
        background=background,
        border=border,
        color=color,
        font_size="0.74rem",
        font_weight="700",
        white_space="nowrap",
    )


def dashboard_pitcher_card(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            dashboard_rank_badge(card["rank"]),
            rx.vstack(
                rx.text(card["pitcher"], font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(card["matchup_line"], font_size="0.84rem", color=COLORS["light_muted"]),
                rx.text(card["metrics"], font_size="0.84rem", color=COLORS["light_muted"], line_height="1.4"),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.spacer(),
            rx.box(
                card["tier"],
                padding="0.34rem 0.64rem",
                border_radius="999px",
                background=COLORS["light_accent_soft"],
                border=f"1px solid {COLORS['light_accent']}",
                color=COLORS["light_accent"],
                font_size="0.74rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="center",
            spacing="3",
        ),
        style={"padding": "0.95rem 1rem"},
    )


def dashboard_compact_list_card(
    title: str,
    eyebrow: str,
    helper: str,
    rows: list[dict[str, str]],
) -> rx.Component:
    return dashboard_surface_card(
        dashboard_section_header(title, helper, eyebrow),
        rx.vstack(
            rx.foreach(
                rows,
                lambda row: rx.hstack(
                    dashboard_rank_badge(row["rank"]),
                rx.vstack(
                    rx.text(row["primary"], font_size="0.92rem", font_weight="800", color=COLORS["light_text"]),
                    rx.text(row["secondary"], font_size="0.8rem", color=COLORS["light_muted"]),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                    rx.cond(
                        row["tertiary"] == "",
                        rx.fragment(),
                        rx.box(
                            row["tertiary"],
                            padding="0.3rem 0.56rem",
                            border_radius="999px",
                            background=COLORS["light_panel_alt"],
                            border=f"1px solid {COLORS['light_border']}",
                            color=COLORS["light_text"],
                            font_size="0.74rem",
                            font_weight="700",
                            white_space="nowrap",
                        ),
                    ),
                    width="100%",
                    align="center",
                    spacing="3",
                    padding="0.25rem 0",
                ),
            ),
            spacing="3",
            width="100%",
        ),
    )


def dashboard_model_mover_card(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.vstack(
            rx.hstack(
                dashboard_rank_badge(card["rank"]),
                rx.vstack(
                    rx.text(card["team"], font_size="0.98rem", font_weight="800", color=COLORS["light_text"]),
                    rx.text(card["driver"], font_size="0.9rem", font_weight="800", color=COLORS["light_accent"]),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                _volatility_badge(card["volatility"]),
                width="100%",
                align="center",
                spacing="3",
            ),
            rx.text(card["metrics"], font_size="0.83rem", color=COLORS["light_muted"], line_height="1.45"),
            spacing="2",
            align="start",
            width="100%",
        ),
        style={"padding": "1rem"},
    )


def decision_banner(title: str, value: str, helper: str, tone: str = "accent") -> rx.Component:
    tone_background = COLORS["light_accent_soft"] if tone == "accent" else COLORS["light_success_soft"]
    tone_border = COLORS["light_accent"] if tone == "accent" else COLORS["light_success"]
    tone_text = COLORS["light_accent"] if tone == "accent" else COLORS["light_success"]
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.box(
                    title,
                    padding="0.22rem 0.52rem",
                    border_radius="999px",
                    background=tone_background,
                    border=f"1px solid {tone_border}",
                    color=tone_text,
                    font_size="0.68rem",
                    font_weight="700",
                ),
                rx.spacer(),
                rx.text(value, font_size="1.6rem", font_weight="800", color=COLORS["light_text"]),
                width="100%",
                align="center",
            ),
            rx.text(helper, font_size="0.9rem", color=COLORS["light_muted"], line_height="1.45", max_width="620px"),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        padding=rx.breakpoints(initial="1rem", md="1.15rem"),
        border_radius="22px",
        background="linear-gradient(180deg, #ffffff 0%, #f7fbff 100%)",
        border=f"1px solid {COLORS['light_border_strong']}",
        box_shadow="0 10px 28px rgba(15, 23, 42, 0.05)",
    )


def intentional_empty_state(title: str, helper: str) -> rx.Component:
    return dashboard_surface_card(
        rx.text("No Active Edge", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
        rx.text(title, font_size="1.05rem", font_weight="800", color=COLORS["light_text"]),
        rx.text(helper, font_size="0.88rem", color=COLORS["light_muted"], line_height="1.45", max_width="520px"),
        style={"background": COLORS["light_panel_alt"]},
    )


def lean_card(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text("Model Lean", font_size="0.7rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(card["matchup"], font_size="0.96rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(f"{card['favorite']} favored by the model", font_size="0.84rem", color=COLORS["light_muted"]),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.box(
                f"{card['win_edge']}%",
                padding="0.32rem 0.58rem",
                border_radius="999px",
                background=COLORS["light_accent_soft"],
                border=f"1px solid {COLORS['light_accent']}",
                color=COLORS["light_accent"],
                font_size="0.74rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="start",
            spacing="3",
        ),
        rx.grid(
            rx.box(
                rx.text("Away", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(f"{card['away_team']} {card['away_win']}%", font_size="0.88rem", font_weight="700", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            rx.box(
                rx.text("Home", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(f"{card['home_team']} {card['home_win']}%", font_size="0.88rem", font_weight="700", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            columns=rx.breakpoints(initial="1", sm="2"),
            spacing="3",
            width="100%",
        ),
        style={"padding": "0.84rem", "box_shadow": "0 8px 20px rgba(15, 23, 42, 0.04)"},
    )


def dashboard_play_card(play: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text(play["bet_type"], font_size="0.7rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(play["pick"], font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(play["matchup"], font_size="0.84rem", color=COLORS["light_muted"]),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.box(
                play["flag"],
                padding="0.32rem 0.58rem",
                border_radius="999px",
                background=rx.cond(
                    play["flag"] == "Strong Bet",
                    COLORS["light_success_soft"],
                    rx.cond(play["flag"] == "Lean", COLORS["light_accent_soft"], COLORS["light_panel_alt"]),
                ),
                border=rx.cond(
                    play["flag"] == "Strong Bet",
                    f"1px solid {COLORS['light_success']}",
                    rx.cond(play["flag"] == "Lean", f"1px solid {COLORS['light_accent']}", f"1px solid {COLORS['light_border']}"),
                ),
                color=rx.cond(
                    play["flag"] == "Strong Bet",
                    COLORS["light_success"],
                    rx.cond(play["flag"] == "Lean", COLORS["light_accent"], COLORS["light_muted"]),
                ),
                font_size="0.72rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="start",
            spacing="3",
        ),
        rx.grid(
            rx.box(
                rx.text("Edge", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(play["edge"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            rx.box(
                rx.text("EV", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(play["ev"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            rx.box(
                rx.text("Line", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(play["line"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            columns=rx.breakpoints(initial="1", sm="3"),
            spacing="3",
            width="100%",
        ),
        style={"padding": "0.95rem"},
    )


def dashboard_driver_card(item: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.text(item["label"], font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
        rx.text(item["team"], font_size="1rem", font_weight="800", color=COLORS["light_text"]),
        rx.text(item["value"], font_size="0.84rem", color=COLORS["light_muted"], line_height="1.4"),
        style={"background": COLORS["light_panel_alt"], "min_height": "118px"},
    )


def market_status_card() -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text("Market Status", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text("Waiting for Edge", font_size="1.18rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(
                    "No positive EV spot is live right now. Watch the strongest model leans and let price movement create the opportunity.",
                    font_size="0.88rem",
                    color=COLORS["light_muted"],
                    line_height="1.45",
                    max_width="560px",
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.box(
                "No Active EV",
                padding="0.38rem 0.68rem",
                border_radius="999px",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                color=COLORS["light_muted"],
                font_size="0.74rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="start",
            spacing="3",
            flex_wrap="wrap",
        ),
        style={"background": "linear-gradient(180deg, #ffffff 0%, #fafbfd 100%)", "padding": "0.88rem"},
    )


def _dashboard_edge_tone(flag):
    return (
        rx.cond(
            flag == "Strong Bet",
            COLORS["light_success"],
            rx.cond(flag == "Lean", "#b45309", COLORS["light_muted"]),
        ),
        rx.cond(
            flag == "Strong Bet",
            COLORS["light_success_soft"],
            rx.cond(flag == "Lean", "rgba(245, 158, 11, 0.12)", COLORS["light_panel_alt"]),
        ),
        rx.cond(
            flag == "Strong Bet",
            f"1px solid {COLORS['light_success']}",
            rx.cond(flag == "Lean", "1px solid #f59e0b", f"1px solid {COLORS['light_border']}"),
        ),
    )


def _dashboard_confidence_badge(group: dict[str, object], tone_color, tone_background, tone_border) -> rx.Component:
    return rx.box(
        group["confidence_label"],
        padding="0.28rem 0.58rem",
        border_radius="999px",
        background=tone_background,
        border=tone_border,
        color=tone_color,
        font_size="0.72rem",
        font_weight="800",
        line_height="1",
        white_space="nowrap",
    )


def _dashboard_driver_line(line: str) -> rx.Component:
    return rx.hstack(
        rx.box(
            width="7px",
            height="7px",
            border_radius="999px",
            background=COLORS["light_accent"],
            flex_shrink="0",
            margin_top="0.28rem",
        ),
        rx.text(line, font_size="0.8rem", color=COLORS["light_text"], line_height="1.35"),
        width="100%",
        align="start",
        spacing="2",
    )


def primary_lean_card(group: dict[str, object]) -> rx.Component:
    edge_text_color, edge_background, edge_border = _dashboard_edge_tone(group["bet_flag"])
    model_pick = rx.cond(group["best_bet"] == "Pass", group["favorite"], group["best_bet"])
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.text("Top Lean", font_size="0.7rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                    width="100%",
                    align="center",
                    spacing="1",
                    flex_wrap="wrap",
                ),
                rx.text(group["matchup_label"], font_size="0.98rem", font_weight="800", color=COLORS["light_text"], line_height="1.18"),
                rx.text(model_pick, font_size="0.82rem", font_weight="700", color=edge_text_color, line_height="1.15"),
                spacing="0",
                align="start",
                min_width="0",
            ),
            rx.spacer(),
            rx.vstack(
                rx.box(
                    rx.text(group["edge_display"], font_size="2.72rem", font_weight="900", color=edge_text_color, line_height="0.88"),
                    padding="0.42rem 0.84rem",
                    border_radius="18px",
                    background=rx.cond(
                        group["bet_flag"] == "Strong Bet",
                        "linear-gradient(180deg, rgba(15, 159, 110, 0.20) 0%, rgba(15, 159, 110, 0.10) 100%)",
                        rx.cond(
                            group["bet_flag"] == "Lean",
                            "linear-gradient(180deg, rgba(245, 158, 11, 0.18) 0%, rgba(245, 158, 11, 0.08) 100%)",
                            edge_background,
                        ),
                    ),
                    border=edge_border,
                    min_width="144px",
                    text_align="right",
                    box_shadow="0 12px 26px rgba(15, 23, 42, 0.07)",
                ),
                _dashboard_confidence_badge(group, edge_text_color, edge_background, edge_border),
                spacing="1",
                align="end",
            ),
            width="100%",
            align="center",
            spacing="1",
            flex_wrap="wrap",
        ),
        rx.grid(
            rx.box(
                rx.hstack(
                    rx.image(src=group["away_logo"], width="34px", height="34px", object_fit="contain"),
                    rx.vstack(
                        rx.text(
                            group["away_team"],
                            font_size="0.82rem",
                            color=rx.cond(
                                group["favorite"] == group["away_team"],
                                COLORS["light_text"],
                                COLORS["light_muted"],
                            ),
                            font_weight=rx.cond(group["favorite"] == group["away_team"], "800", "700"),
                            line_height="1.1",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    width="100%",
                    align="center",
                    spacing="2",
                ),
                padding="0.58rem 0.74rem",
                background=rx.cond(
                    group["favorite"] == group["away_team"],
                    COLORS["light_chip"],
                    COLORS["light_panel_alt"],
                ),
                border=rx.cond(
                    group["favorite"] == group["away_team"],
                    f"1px solid {COLORS['light_accent']}",
                    f"1px solid {COLORS['light_border']}",
                ),
                border_radius="16px",
            ),
            rx.box(
                rx.hstack(
                    rx.image(src=group["home_logo"], width="34px", height="34px", object_fit="contain"),
                    rx.vstack(
                        rx.text(
                            group["home_team"],
                            font_size="0.82rem",
                            color=rx.cond(
                                group["favorite"] == group["home_team"],
                                COLORS["light_text"],
                                COLORS["light_muted"],
                            ),
                            font_weight=rx.cond(group["favorite"] == group["home_team"], "800", "700"),
                            line_height="1.1",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    width="100%",
                    align="center",
                    spacing="2",
                ),
                padding="0.58rem 0.74rem",
                background=rx.cond(
                    group["favorite"] == group["home_team"],
                    COLORS["light_chip"],
                    COLORS["light_panel_alt"],
                ),
                border=rx.cond(
                    group["favorite"] == group["home_team"],
                    f"1px solid {COLORS['light_accent']}",
                    f"1px solid {COLORS['light_border']}",
                ),
                border_radius="16px",
            ),
            columns=rx.breakpoints(initial="1", sm="2"),
            spacing="2",
            width="100%",
        ),
        rx.box(
            rx.vstack(
                rx.text(
                    rx.cond(
                        group["probability_line"] == "",
                        f"{group['away_team']} | {group['home_team']}",
                        group["probability_line"],
                    ),
                    font_size="0.78rem",
                    color=COLORS["light_text"],
                    font_weight="700",
                    white_space="nowrap",
                    overflow="hidden",
                    text_overflow="ellipsis",
                    width="100%",
                ),
                rx.box(
                    rx.hstack(
                        rx.box(
                            width=f"{group['away_win']}%",
                            min_width="12%",
                            height="19px",
                            border_radius="999px",
                            background=group["away_primary"],
                        ),
                        rx.box(
                            width=f"{group['home_win']}%",
                            min_width="12%",
                            height="19px",
                            border_radius="999px",
                            background=group["home_primary"],
                        ),
                        spacing="1",
                        width="100%",
                        height="19px",
                        align="center",
                    ),
                    width="100%",
                    padding="3px",
                    border_radius="999px",
                    background="#eef2f7",
                    border=f"1px solid {COLORS['light_border_strong']}",
                ),
                rx.box(
                    rx.hstack(
                        rx.vstack(
                            rx.text("Model Lean", font_size="0.66rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.text(model_pick, font_size="0.94rem", font_weight="800", color=COLORS["light_text"], line_height="1.2"),
                            spacing="1",
                            align="start",
                        ),
                        rx.spacer(),
                        rx.vstack(
                            rx.text("Projected Total", font_size="0.66rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.text(group["projected_total"], font_size="0.94rem", font_weight="800", color=COLORS["light_text"], line_height="1.2"),
                            rx.text(group["projected_score"], font_size="0.76rem", color=COLORS["light_muted"]),
                            spacing="1",
                            align="end",
                        ),
                        width="100%",
                        align="start",
                        spacing="3",
                    ),
                    padding="0.6rem 0.74rem",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="16px",
                    width="100%",
                ),
                spacing="1",
            ),
            width="100%",
            padding="0",
        ),
        rx.box(
            rx.vstack(
                rx.text("Why It Matters", font_size="0.68rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.cond(
                    group["driver_1"] == "",
                    rx.text(
                        "No major driver signals",
                        font_size="0.8rem",
                        color=COLORS["light_muted"],
                        line_height="1.35",
                    ),
                    rx.vstack(
                        _dashboard_driver_line(group["driver_1"]),
                        rx.cond(
                            group["driver_2"] == "",
                            rx.fragment(),
                            _dashboard_driver_line(group["driver_2"]),
                        ),
                        rx.cond(
                            group["driver_3"] == "",
                            rx.fragment(),
                            _dashboard_driver_line(group["driver_3"]),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            padding="0.64rem 0.76rem",
            background=COLORS["light_panel_alt"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="16px",
            width="100%",
        ),
        style={
            "padding": "0.76rem",
            "box_shadow": "0 12px 30px rgba(15, 23, 42, 0.07)",
            "border": f"1px solid {COLORS['light_border_strong']}",
        },
    )


def compact_watch_matchup(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text(card["matchup"], font_size="0.92rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(f"{card['favorite']} favored | Total {card['projected_total']}", font_size="0.82rem", color=COLORS["light_muted"]),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.box(
                card["bet_flag"],
                padding="0.28rem 0.52rem",
                border_radius="999px",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                color=COLORS["light_muted"],
                font_size="0.72rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="center",
            spacing="3",
        ),
        style={"padding": "0.9rem", "box_shadow": "none"},
    )


def dashboard_matchup_card(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.hstack(
                rx.image(src=card["away_logo"], alt=card["away_team"], width="34px", height="34px", object_fit="contain"),
                rx.text(card["away_team"], font_size="0.92rem", font_weight="700", color=COLORS["light_text"]),
                spacing="2",
                align="center",
            ),
            rx.text("at", font_size="0.75rem", color=COLORS["light_muted_2"], font_weight="700"),
            rx.hstack(
                rx.image(src=card["home_logo"], alt=card["home_team"], width="34px", height="34px", object_fit="contain"),
                rx.text(card["home_team"], font_size="0.92rem", font_weight="700", color=COLORS["light_text"]),
                spacing="2",
                align="center",
            ),
            rx.spacer(),
            rx.box(
                card["bet_flag"],
                padding="0.3rem 0.56rem",
                border_radius="999px",
                background=rx.cond(
                    card["bet_flag"] == "Strong Bet",
                    COLORS["light_success_soft"],
                    rx.cond(card["bet_flag"] == "Lean", COLORS["light_accent_soft"], COLORS["light_panel_alt"]),
                ),
                border=rx.cond(
                    card["bet_flag"] == "Strong Bet",
                    f"1px solid {COLORS['light_success']}",
                    rx.cond(card["bet_flag"] == "Lean", f"1px solid {COLORS['light_accent']}", f"1px solid {COLORS['light_border']}"),
                ),
                color=rx.cond(
                    card["bet_flag"] == "Strong Bet",
                    COLORS["light_success"],
                    rx.cond(card["bet_flag"] == "Lean", COLORS["light_accent"], COLORS["light_muted"]),
                ),
                font_size="0.72rem",
                font_weight="700",
                white_space="nowrap",
            ),
            width="100%",
            align="center",
            spacing="3",
            flex_wrap="wrap",
        ),
        rx.grid(
            rx.box(
                rx.text("Win Split", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(f"{card['away_win']}% / {card['home_win']}%", font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            rx.box(
                rx.text("Projected Total", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(card["projected_total"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            rx.box(
                rx.text("Model Lean", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(card["favorite"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
            ),
            columns=rx.breakpoints(initial="1", sm="3"),
            spacing="3",
            width="100%",
        ),
        rx.text(
            f"{card['away_pitcher']} vs {card['home_pitcher']}",
            font_size="0.82rem",
            color=COLORS["light_muted"],
        ),
        style={"padding": "0.95rem"},
    )


def _daily_status_badge(label: str) -> rx.Component:
    background = rx.cond(
        label == "Best Bet",
        COLORS["light_success_soft"],
        rx.cond(
            label == "Positive EV",
            "rgba(37, 99, 235, 0.10)",
            rx.cond(
                label == "Strong",
                COLORS["light_success_soft"],
                rx.cond(
                    label == "Lean",
                    COLORS["light_accent_soft"],
                    rx.cond(label == "Pass", COLORS["light_panel_alt"], "rgba(15, 23, 42, 0.04)"),
                ),
            ),
        ),
    )
    border = rx.cond(
        label == "Best Bet",
        "1px solid rgba(15, 159, 110, 0.20)",
        rx.cond(
            label == "Positive EV",
            "1px solid rgba(37, 99, 235, 0.18)",
            rx.cond(
                label == "Strong",
                f"1px solid {COLORS['light_success']}",
                rx.cond(
                    label == "Lean",
                    f"1px solid {COLORS['light_accent']}",
                    f"1px solid {COLORS['light_border']}",
                ),
            ),
        ),
    )
    color = rx.cond(
        label == "Best Bet",
        COLORS["light_success"],
        rx.cond(
            label == "Positive EV",
            COLORS["light_accent"],
            rx.cond(label == "Strong", COLORS["light_success"], rx.cond(label == "Lean", COLORS["light_accent"], COLORS["light_muted"])),
        ),
    )
    return rx.box(
        label,
        padding="0.36rem 0.66rem",
        border_radius="999px",
        background=background,
        border=border,
        color=color,
        font_size="0.72rem",
        font_weight="800",
        white_space="nowrap",
    )


def _daily_ev_badge(label: str) -> rx.Component:
    background = rx.cond(
        label == "Positive EV",
        COLORS["light_success_soft"],
        rx.cond(label == "Waiting for market", "rgba(0,0,0,0.06)", "rgba(15, 23, 42, 0.04)"),
    )
    border = rx.cond(
        label == "Positive EV",
        f"1px solid {COLORS['light_success']}",
        rx.cond(label == "Waiting for market", "1px solid rgba(0,0,0,0.08)", f"1px solid {COLORS['light_border']}"),
    )
    color = rx.cond(
        label == "Positive EV",
        COLORS["light_success"],
        rx.cond(label == "Waiting for market", "#475569", COLORS["light_text"]),
    )
    return rx.box(
        label,
        padding="0.42rem 0.78rem",
        border_radius="999px",
        background=background,
        border=border,
        color=color,
        font_size="0.74rem",
        font_weight="800",
        white_space="nowrap",
    )


def _daily_driver_tag(label: str) -> rx.Component:
    return rx.box(
        label,
        padding="0.3rem 0.56rem",
        border_radius="999px",
        background=COLORS["light_panel_alt"],
        border=f"1px solid {COLORS['light_border']}",
        color=COLORS["light_text"],
        font_size="0.74rem",
        font_weight="700",
        white_space="nowrap",
    )


def top_bet_hero_card(card: dict[str, str]) -> rx.Component:
    border_color = rx.cond(
        card["status_label"] == "Strong",
        "rgba(15, 159, 110, 0.22)",
        "rgba(37, 99, 235, 0.18)",
    )
    background_tint = rx.cond(
        card["status_label"] == "Strong",
        "linear-gradient(180deg, rgba(15, 159, 110, 0.06) 0%, #ffffff 100%)",
        "linear-gradient(180deg, rgba(37, 99, 235, 0.05) 0%, #ffffff 100%)",
    )
    return rx.box(
        rx.vstack(
            rx.hstack(
                dashboard_section_header(
                    "Top Bet of the Day",
                    "The single best available edge on the current board, ranked by positive EV first.",
                    "Best Available Edge",
                ),
                rx.spacer(),
                _daily_status_badge(card["status_label"]),
                width="100%",
                align="start",
                spacing="3",
                flex_wrap="wrap",
            ),
            rx.grid(
                rx.box(
                    rx.vstack(
                        rx.text(card["matchup_label"], font_size="1.12rem", font_weight="800", color=COLORS["light_text"]),
                        rx.cond(
                            (card["away_pitcher"] == "") | (card["away_pitcher"] == "undefined") | (card["home_pitcher"] == "") | (card["home_pitcher"] == "undefined"),
                            rx.fragment(),
                            rx.text(
                                f"{card['away_pitcher']} vs {card['home_pitcher']}",
                                font_size="0.84rem",
                                color=COLORS["light_muted"],
                            ),
                        ),
                        rx.text(f"Model Lean: {card['model_lean']}", font_size="0.9rem", font_weight="700", color=COLORS["light_text"]),
                        rx.hstack(
                            rx.text("Confidence", font_size="0.72rem", color=COLORS["light_muted_2"], font_weight="700", text_transform="uppercase", letter_spacing="0.12em"),
                            _daily_status_badge(card["status_label"]),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.text(f"Fair: {card['fair_price']}", font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                        rx.text(f"Market: {card['market_price']}", font_size="0.9rem", color=COLORS["light_text"]),
                        rx.text(f"Edge: {card['edge_cents']}", font_size="0.88rem", color=COLORS["light_muted"]),
                        _daily_ev_badge(card["ev_status"]),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.cond(
                            (card["projected_total"] == "") | (card["projected_total"] == "undefined"),
                            rx.fragment(),
                            rx.text(f"Projected Total: {card['projected_total']}", font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                        ),
                        rx.cond(
                            (card["run_split"] == "") | (card["run_split"] == "undefined"),
                            rx.fragment(),
                            rx.text(card["run_split"], font_size="0.84rem", color=COLORS["light_muted"]),
                        ),
                        rx.text("Why It Matters", font_size="0.72rem", color=COLORS["light_muted_2"], font_weight="700", text_transform="uppercase", letter_spacing="0.12em"),
                        rx.flex(
                            _daily_driver_tag(card["driver_1"]),
                            rx.cond(card["driver_2"] == "", rx.fragment(), _daily_driver_tag(card["driver_2"])),
                            rx.cond(card["driver_3"] == "", rx.fragment(), _daily_driver_tag(card["driver_3"])),
                            wrap="wrap",
                            gap="0.5rem",
                            width="100%",
                        ),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                    width="100%",
                ),
                columns=rx.breakpoints(initial="1", lg="3"),
                spacing="5",
                width="100%",
            ),
            spacing="4",
            align="start",
            width="100%",
        ),
        width="100%",
        padding=rx.breakpoints(initial="1.05rem", md="1.2rem"),
        background=background_tint,
        border=f"1px solid {border_color}",
        border_radius="24px",
        box_shadow="0 10px 28px rgba(15, 23, 42, 0.07)",
    )


def top_bet_empty_state() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                dashboard_section_header(
                    "Top Bet of the Day",
                    "The hero slot activates automatically as soon as live market prices create a real edge.",
                    "Best Available Edge",
                ),
                rx.spacer(),
                _daily_ev_badge("Waiting for market"),
                width="100%",
                align="start",
                spacing="3",
                flex_wrap="wrap",
            ),
            rx.text("No top bet yet", font_size="1.08rem", font_weight="800", color=COLORS["light_text"]),
            rx.text(
                "Waiting for market prices to identify the strongest edge on the board.",
                font_size="0.9rem",
                color=COLORS["light_muted"],
                line_height="1.45",
            ),
            rx.text("Model leans are still shown below.", font_size="0.82rem", color=COLORS["light_muted_2"]),
            spacing="3",
            align="start",
            width="100%",
        ),
        width="100%",
        padding=rx.breakpoints(initial="1.05rem", md="1.2rem"),
        background="linear-gradient(180deg, rgba(15, 23, 42, 0.02) 0%, #ffffff 100%)",
        border="1px solid rgba(0,0,0,0.06)",
        border_radius="24px",
        box_shadow="0 8px 22px rgba(15, 23, 42, 0.05)",
    )


def coming_soon_card(title: str) -> rx.Component:
    return dashboard_surface_card(
        rx.text("Coming Soon", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
        rx.text(title, font_size="1.02rem", font_weight="800", color=COLORS["light_text"]),
        rx.text(
            "This section will populate once simulation and pipeline data is available.",
            font_size="0.86rem",
            color=COLORS["light_muted"],
            line_height="1.45",
        ),
        style={"min_height": "150px"},
    )


def _projection_tier_badge(tag: str, tier: str) -> rx.Component:
    tier_background = (
        "linear-gradient(180deg, rgba(37, 99, 235, 0.14) 0%, rgba(37, 99, 235, 0.08) 100%)"
        if tier == "elite"
        else (
            "linear-gradient(180deg, rgba(15, 159, 110, 0.14) 0%, rgba(15, 159, 110, 0.08) 100%)"
            if tier == "playoff"
            else (COLORS["light_panel_alt"] if tier == "fringe" else "rgba(15, 23, 42, 0.03)")
        )
    )
    tier_border = (
        "1px solid rgba(37, 99, 235, 0.24)"
        if tier == "elite"
        else (
            "1px solid rgba(15, 159, 110, 0.22)"
            if tier == "playoff"
            else (f"1px solid {COLORS['light_border']}" if tier == "fringe" else "1px solid rgba(15, 23, 42, 0.06)")
        )
    )
    tier_color = (
        COLORS["light_accent"]
        if tier == "elite"
        else (
            COLORS["light_success"]
            if tier == "playoff"
            else (COLORS["light_text"] if tier == "fringe" else COLORS["light_muted"])
        )
    )
    return rx.box(
        tag,
        padding="0.26rem 0.56rem",
        border_radius="999px",
        background=tier_background,
        border=tier_border,
        color=tier_color,
        font_size="0.7rem",
        font_weight="800",
        white_space="nowrap",
        letter_spacing="0.01em",
        min_width="86px",
        text_align="center",
        display="inline-flex",
        align_items="center",
        justify_content="center",
    )


def projection_tier_card(title: str, rows: list[dict[str, str]]) -> rx.Component:
    tier_key = "elite" if "Elite" in title else ("playoff" if "Playoff" in title else ("fringe" if "Fringe" in title else "rebuilding"))
    return dashboard_surface_card(
        dashboard_section_header(title, None, "Tier View"),
        rx.cond(
            rows.length() == 0,
            rx.box(
                rx.vstack(
                    rx.text(
                        rx.cond(tier_key == "rebuilding", "No teams currently in the rebuilding bucket.", "No teams currently fit this tier."),
                        font_size="0.86rem",
                        font_weight="800",
                        color=COLORS["light_text"],
                    ),
                    rx.text(
                        rx.cond(
                            tier_key == "rebuilding",
                            "The current projection set still sees enough competitive shape across the league that nobody falls into the bottom tier.",
                            "As projections shift, this tier will populate automatically without changing the layout.",
                        ),
                        font_size="0.8rem",
                        color=COLORS["light_muted"],
                        line_height="1.45",
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                padding="0.85rem 0.9rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="16px",
                width="100%",
            ),
            rx.vstack(
                rx.foreach(
                    rows,
                    lambda row: rx.box(
                        rx.hstack(
                            rx.text(
                                row["rank"],
                                font_size="0.8rem",
                                font_weight="900",
                                color=COLORS["light_muted_2"],
                                min_width="24px",
                            ),
                            rx.text(row["team"], font_size="0.91rem", font_weight="800", color=COLORS["light_text"]),
                            rx.spacer(),
                            rx.text(row["detail"], font_size="0.79rem", color=COLORS["light_muted"], min_width="76px", text_align="right"),
                            _projection_tier_badge(row["tag"], tier_key),
                            spacing="3",
                            align="center",
                            width="100%",
                        ),
                        padding="0.62rem 0.8rem",
                        background=COLORS["light_panel_alt"],
                        border=f"1px solid {COLORS['light_border']}",
                        border_radius="14px",
                        width="100%",
                        transition="all 160ms ease",
                        _hover={
                            "background": "#f4f8fc",
                            "box_shadow": "0 8px 18px rgba(15, 23, 42, 0.05)",
                            "transform": "translateY(-1px)",
                        },
                    ),
                ),
                spacing="2",
                width="100%",
            ),
        ),
        style={"padding": "0.95rem 1rem"},
    )


def _support_empty_preview(title: str) -> rx.Component:
    if title == "Current Division Standings":
        return rx.vstack(
            rx.text("Preview", font_size="0.96rem", font_weight="800", color=COLORS["light_text"]),
            rx.text(
                "Division summaries will drop into this compact race board once the full standings feed is wired through.",
                font_size="0.84rem",
                color=COLORS["light_muted"],
                line_height="1.45",
            ),
            rx.vstack(
                rx.foreach(
                    ["AL East leader snapshot", "NL West pressure race", "Wild card cutline context"],
                    lambda item: rx.vstack(
                        rx.text(item, font_size="0.77rem", color=COLORS["light_text"], font_weight="700"),
                        rx.box(height="1px", width="100%", background=COLORS["light_border"]),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        )
    if title == "Playoff Odds":
        return rx.vstack(
            rx.text("Preview", font_size="0.96rem", font_weight="800", color=COLORS["light_text"]),
            rx.text(
                "This quick-read odds panel is designed for league-wide playoff context without opening a dense table.",
                font_size="0.84rem",
                color=COLORS["light_muted"],
                line_height="1.45",
            ),
            rx.vstack(
                rx.foreach(
                    [(78, "Top tier"), (56, "In the mix"), (33, "Longer shot")],
                    lambda item: rx.vstack(
                        rx.hstack(
                            rx.text(item[1], font_size="0.72rem", color=COLORS["light_muted"], min_width="64px"),
                            rx.box(
                                rx.box(
                                    width=f"{item[0]}%",
                                    height="10px",
                                    border_radius="999px",
                                    background="linear-gradient(90deg, rgba(37, 99, 235, 0.16) 0%, rgba(37, 99, 235, 0.08) 100%)",
                                ),
                                width="100%",
                                height="10px",
                                border_radius="999px",
                                background="rgba(15, 23, 42, 0.05)",
                                overflow="hidden",
                            ),
                            rx.text(f"{item[0]}%", font_size="0.72rem", color=COLORS["light_muted_2"], min_width="34px", text_align="right"),
                            spacing="2",
                            width="100%",
                            align="center",
                        ),
                        spacing="1",
                        align="start",
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            align="start",
            width="100%",
        )
    return rx.vstack(
        rx.text("Preview", font_size="0.96rem", font_weight="800", color=COLORS["light_text"]),
        rx.text(
            "Saved model outputs will stack here as compact preview cards once the latest prediction history is fully connected.",
            font_size="0.84rem",
            color=COLORS["light_muted"],
            line_height="1.45",
        ),
        rx.vstack(
            rx.foreach(
                ["Recent saved model snapshot", "Latest no-vig comparison", "Top recommendation preview"],
                lambda item: rx.box(
                    rx.text(item, font_size="0.78rem", color=COLORS["light_muted"]),
                    width="100%",
                    padding="0.72rem 0.78rem",
                    border_radius="14px",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    box_shadow="0 4px 12px rgba(15, 23, 42, 0.03)",
                ),
            ),
            spacing="2",
            width="100%",
        ),
        spacing="3",
        align="start",
        width="100%",
    )


def _support_live_rows(title: str, rows: list[dict[str, str]]) -> rx.Component:
    if title == "Current Division Standings":
        return rx.vstack(
            rx.foreach(
                rows,
                lambda row: rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text(row["team"], font_size="0.92rem", font_weight="800", color=COLORS["light_text"]),
                            rx.text(row["detail"], font_size="0.79rem", color=COLORS["light_muted"]),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.box(height="1px", width="100%", background=COLORS["light_border"]),
                    spacing="2",
                    align="start",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        )
    if title == "Playoff Odds":
        return rx.vstack(
            rx.foreach(
                rows,
                lambda row, idx: rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.text(row["team"], font_size="0.9rem", font_weight="800", color=COLORS["light_text"]),
                            rx.spacer(),
                            rx.box(
                                "Odds",
                                padding="0.22rem 0.48rem",
                                border_radius="999px",
                                background=COLORS["light_panel"],
                                border=f"1px solid {COLORS['light_border']}",
                                color=COLORS["light_muted_2"],
                                font_size="0.68rem",
                                font_weight="700",
                            ),
                            width="100%",
                            align="center",
                        ),
                        rx.box(
                            rx.box(
                                width=rx.cond(
                                    idx == 0,
                                    "78%",
                                    rx.cond(idx == 1, "61%", rx.cond(idx == 2, "43%", "52%")),
                                ),
                                height="8px",
                                border_radius="999px",
                                background="linear-gradient(90deg, rgba(37, 99, 235, 0.16) 0%, rgba(37, 99, 235, 0.08) 100%)",
                            ),
                            width="100%",
                            height="8px",
                            border_radius="999px",
                            background="rgba(15, 23, 42, 0.05)",
                            overflow="hidden",
                        ),
                        rx.text(row["detail"], font_size="0.79rem", color=COLORS["light_muted"]),
                        spacing="2",
                        align="start",
                        width="100%",
                    ),
                        padding="0.74rem 0.8rem",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="14px",
                    width="100%",
                ),
            ),
            spacing="2",
            width="100%",
        )
    return rx.vstack(
        rx.foreach(
            rows,
            lambda row: rx.box(
                rx.vstack(
                    rx.text(row["team"], font_size="0.91rem", font_weight="800", color=COLORS["light_text"]),
                    rx.text(row["detail"], font_size="0.79rem", color=COLORS["light_muted"]),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                padding="0.72rem 0.8rem",
                background=COLORS["light_panel_alt"],
                border=f"1px solid {COLORS['light_border']}",
                border_radius="14px",
                width="100%",
                box_shadow="0 4px 12px rgba(15, 23, 42, 0.03)",
            ),
        ),
        spacing="2",
        width="100%",
    )


def outlook_support_card(title: str, helper: str, rows: list[dict[str, str]]) -> rx.Component:
    return dashboard_surface_card(
        dashboard_section_header(title, helper, "Support"),
        rx.cond(
            rows.length() == 0,
            _support_empty_preview(title),
            _support_live_rows(title, rows),
        ),
        style={"padding": "1rem", "min_height": "236px"},
    )


def daily_matchup_board_card(card: dict[str, str]) -> rx.Component:
    return dashboard_surface_card(
        rx.hstack(
            rx.vstack(
                rx.text("Matchup", font_size="0.68rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(card["matchup_label"], font_size="1.04rem", font_weight="800", color=COLORS["light_text"], line_height="1.15"),
                rx.text(
                    f"{card['away_pitcher']} vs {card['home_pitcher']}",
                    font_size="0.82rem",
                    color=COLORS["light_muted"],
                ),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            _daily_status_badge(card["grid_badge"]),
            width="100%",
            align="start",
            spacing="3",
            flex_wrap="wrap",
        ),
        rx.box(
            rx.vstack(
                rx.box(
                    rx.hstack(
                        rx.vstack(
                            rx.hstack(
                                rx.image(src=card["away_logo"], alt=card["away_team"], width="26px", height="26px", object_fit="contain"),
                                rx.text(card["away_abbr"], font_size="0.76rem", font_weight="800", color=COLORS["light_text"]),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(f"{card['away_win']}%", font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                            rx.text(card["away_fair_ml"], font_size="0.78rem", color=COLORS["light_muted"]),
                            spacing="1",
                            align="start",
                            min_width="90px",
                        ),
                        rx.box(
                            rx.hstack(
                                rx.box(
                                    width=f"{card['away_win']}%",
                                    min_width="12%",
                                    height="18px",
                                    border_radius="999px",
                                    background=card["away_primary"],
                                    box_shadow=f"0 0 14px {card['away_primary']}33",
                                ),
                                rx.box(
                                    width=f"{card['home_win']}%",
                                    min_width="12%",
                                    height="18px",
                                    border_radius="999px",
                                    background=card["home_primary"],
                                    box_shadow=f"0 0 14px {card['home_primary']}33",
                                ),
                                spacing="1",
                                width="100%",
                                height="18px",
                                align="center",
                            ),
                            width="100%",
                            padding="3px",
                            border_radius="999px",
                            background="#eef2f7",
                            border=f"1px solid {COLORS['light_border_strong']}",
                        ),
                        rx.vstack(
                            rx.hstack(
                                rx.text(card["home_abbr"], font_size="0.76rem", font_weight="800", color=COLORS["light_text"]),
                                rx.image(src=card["home_logo"], alt=card["home_team"], width="26px", height="26px", object_fit="contain"),
                                spacing="2",
                                align="center",
                            ),
                            rx.text(f"{card['home_win']}%", font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                            rx.text(card["home_fair_ml"], font_size="0.78rem", color=COLORS["light_muted"]),
                            spacing="1",
                            align="end",
                            min_width="90px",
                        ),
                        spacing="3",
                        width="100%",
                        align="center",
                    ),
                    padding="0.8rem 0.85rem",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="16px",
                    width="100%",
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        rx.box(
            rx.cond(
                card["market_available"] == "true",
                rx.vstack(
                    rx.hstack(
                        rx.vstack(
                            rx.text("Decision", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                            rx.text(card["model_lean"], font_size="1.12rem", font_weight="800", color=COLORS["light_text"]),
                            rx.cond(
                                (card["fair_price"] == "") | (card["fair_price"] == "-") | (card["fair_price"] == "N/A"),
                                rx.fragment(),
                                rx.text(f"Fair: {card['fair_price']}", font_size="0.83rem", font_weight="600", color=COLORS["light_muted"]),
                            ),
                            spacing="1",
                            align="start",
                        ),
                        rx.spacer(),
                        rx.vstack(
                            rx.text(f"Market: {card['market_price']}", font_size="0.84rem", font_weight="600", color=COLORS["light_text"]),
                            rx.text(f"Edge: {card['edge_cents']}", font_size="0.82rem", font_weight="600", color=COLORS["light_muted"]),
                            spacing="1",
                            align="end",
                        ),
                        width="100%",
                        align="start",
                        spacing="3",
                    ),
                    rx.hstack(
                        rx.spacer(),
                        _daily_ev_badge(card["ev_status"]),
                        width="100%",
                        align="center",
                    ),
                    spacing="3",
                    width="100%",
                    align="start",
                ),
                rx.vstack(
                    rx.text("Decision", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                    rx.text(card["model_lean"], font_size="1.12rem", font_weight="800", color=COLORS["light_text"]),
                    rx.cond(
                        (card["fair_price"] == "") | (card["fair_price"] == "-") | (card["fair_price"] == "N/A"),
                        rx.fragment(),
                        rx.text(f"Fair: {card['fair_price']}", font_size="0.83rem", font_weight="600", color=COLORS["light_muted"]),
                    ),
                    rx.hstack(
                        _daily_ev_badge("Waiting for market"),
                        width="100%",
                        align="center",
                    ),
                    spacing="2",
                    width="100%",
                    align="start",
                ),
            ),
            padding="1.3rem 1.34rem",
            background=rx.cond(
                card["grid_state"] == "Best Bet",
                "rgba(15, 159, 110, 0.06)",
                rx.cond(
                    card["grid_state"] == "Positive EV",
                    "rgba(37, 99, 235, 0.05)",
                    rx.cond(
                        card["status_label"] == "Strong",
                        "rgba(15, 159, 110, 0.05)",
                        rx.cond(
                            card["status_label"] == "Lean",
                            "rgba(37, 99, 235, 0.05)",
                            "rgba(0,0,0,0.02)",
                        ),
                    ),
                ),
            ),
            border=rx.cond(
                card["grid_state"] == "Best Bet",
                "1px solid rgba(15, 159, 110, 0.22)",
                rx.cond(
                    card["grid_state"] == "Positive EV",
                    "1px solid rgba(37, 99, 235, 0.18)",
                    rx.cond(
                        card["status_label"] == "Strong",
                        "1px solid rgba(15, 159, 110, 0.16)",
                        rx.cond(
                            card["status_label"] == "Lean",
                            "1px solid rgba(37, 99, 235, 0.16)",
                            "1px solid rgba(0,0,0,0.08)",
                        ),
                    ),
                ),
            ),
            border_radius="16px",
            width="100%",
            box_shadow="0 4px 12px rgba(0,0,0,0.06)",
        ),
        rx.box(
            rx.box(
                rx.text("Projected Total", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(card["projected_total"], font_size="1rem", font_weight="800", color=COLORS["light_text"]),
                rx.text(card["run_split"], font_size="0.8rem", color=COLORS["light_muted"]),
                spacing="1",
                align="start",
            ),
            padding="0.82rem 0.88rem",
            background=COLORS["light_panel_alt"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="16px",
            width="100%",
        ),
        rx.box(
            rx.vstack(
                rx.text("Why It Matters", font_size="0.68rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.flex(
                    _daily_driver_tag(card["driver_1"]),
                    rx.cond(card["driver_2"] == "", rx.fragment(), _daily_driver_tag(card["driver_2"])),
                    rx.cond(card["driver_3"] == "", rx.fragment(), _daily_driver_tag(card["driver_3"])),
                    wrap="wrap",
                    gap="0.5rem",
                    width="100%",
                ),
                spacing="2",
                align="start",
                width="100%",
            ),
            padding="0.78rem 0.84rem",
            background=COLORS["light_panel_alt"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="16px",
            width="100%",
        ),
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.vstack(
                        rx.text("Market Detail", font_size="0.68rem", letter_spacing="0.12em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                        rx.text("Open a single-game totals snapshot only when you need deeper market context.", font_size="0.78rem", color=COLORS["light_muted"], line_height="1.45"),
                        spacing="1",
                        align="start",
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.cond(card["details_open"] == "true", "Hide Detail", "Open Detail"),
                        on_click=lambda: AppState.toggle_matchup_totals_detail(
                            card["matchup"],
                            card["away_team"],
                            card["home_team"],
                        ),
                        background=COLORS["light_panel"],
                        color=COLORS["light_text"],
                        border=f"1px solid {COLORS['light_border_strong']}",
                        border_radius="10px",
                        padding="0.48rem 0.78rem",
                        font_size="0.76rem",
                        font_weight="700",
                        _hover={"background": COLORS["light_panel_alt"]},
                    ),
                    width="100%",
                    align="center",
                    spacing="3",
                ),
                rx.cond(
                    card["details_open"] == "true",
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.box(
                                    rx.vstack(
                                        rx.text("Total", font_size="0.67rem", text_transform="uppercase", letter_spacing="0.12em", color=COLORS["light_muted_2"], font_weight="700"),
                                        rx.text(card["totals_market_line"], font_size="1.08rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.03em"),
                                        rx.text("Market line", font_size="0.74rem", color=COLORS["light_muted"]),
                                        spacing="1",
                                        align="start",
                                    ),
                                    padding="0.82rem 0.88rem",
                                    background="linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    border_radius="16px",
                                    min_width="110px",
                                    box_shadow="0 8px 18px rgba(15, 23, 42, 0.04)",
                                ),
                                rx.box(
                                    rx.vstack(
                                        rx.text("Over", font_size="0.67rem", text_transform="uppercase", letter_spacing="0.12em", color=COLORS["light_muted_2"], font_weight="700"),
                                        rx.text(card["totals_over_price"], font_size="1.08rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.03em"),
                                        rx.text("Price", font_size="0.74rem", color=COLORS["light_muted"]),
                                        spacing="1",
                                        align="start",
                                    ),
                                    padding="0.82rem 0.88rem",
                                    background="linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    border_radius="16px",
                                    min_width="110px",
                                    box_shadow="0 8px 18px rgba(15, 23, 42, 0.04)",
                                ),
                                rx.box(
                                    rx.vstack(
                                        rx.text("Under", font_size="0.67rem", text_transform="uppercase", letter_spacing="0.12em", color=COLORS["light_muted_2"], font_weight="700"),
                                        rx.text(card["totals_under_price"], font_size="1.08rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.03em"),
                                        rx.text("Price", font_size="0.74rem", color=COLORS["light_muted"]),
                                        spacing="1",
                                        align="start",
                                    ),
                                    padding="0.82rem 0.88rem",
                                    background="linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    border_radius="16px",
                                    min_width="110px",
                                    box_shadow="0 8px 18px rgba(15, 23, 42, 0.04)",
                                ),
                                spacing="3",
                                flex_wrap="wrap",
                                width="100%",
                            ),
                            rx.box(
                                rx.vstack(
                                    rx.hstack(
                                        rx.box(
                                            f"Source: {card['totals_source']}",
                                            padding="0.28rem 0.58rem",
                                            border_radius="999px",
                                            background=COLORS["light_chip"],
                                            border=f"1px solid {COLORS['light_border']}",
                                            font_size="0.73rem",
                                            font_weight="700",
                                            color=COLORS["light_text"],
                                        ),
                                        rx.box(
                                            f"Updated {card['totals_last_refreshed_at']}",
                                            padding="0.28rem 0.58rem",
                                            border_radius="999px",
                                            background=COLORS["light_panel"],
                                            border=f"1px solid {COLORS['light_border']}",
                                            font_size="0.73rem",
                                            font_weight="700",
                                            color=COLORS["light_muted"],
                                        ),
                                        spacing="2",
                                        flex_wrap="wrap",
                                        width="100%",
                                        align="center",
                                    ),
                                    rx.text(card["totals_subheadline"], font_size="0.8rem", color=COLORS["light_muted"], line_height="1.45"),
                                    spacing="2",
                                    align="start",
                                    width="100%",
                                ),
                                padding="0.78rem 0.84rem",
                                background="rgba(255,255,255,0.7)",
                                border=f"1px solid {COLORS['light_border']}",
                                border_radius="16px",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text(
                                    card["totals_headline"],
                                    font_size="0.82rem",
                                    font_weight="800",
                                    color=COLORS["light_text"],
                                ),
                                rx.spacer(),
                                rx.button(
                                    "Refresh Detail",
                                    on_click=lambda: AppState.refresh_matchup_totals_detail(
                                        card["matchup"],
                                        card["away_team"],
                                        card["home_team"],
                                    ),
                                    background=COLORS["light_panel"],
                                    color=COLORS["light_text"],
                                    border=f"1px solid {COLORS['light_border_strong']}",
                                    border_radius="10px",
                                    padding="0.44rem 0.72rem",
                                    font_size="0.74rem",
                                    font_weight="700",
                                    _hover={"background": COLORS["light_panel_alt"]},
                                ),
                                width="100%",
                                align="center",
                                spacing="3",
                                flex_wrap="wrap",
                            ),
                            rx.box(
                                rx.text(card["totals_quota_note"], font_size="0.75rem", color=COLORS["light_muted_2"], line_height="1.45"),
                                padding="0.7rem 0.78rem",
                                background="rgba(255,255,255,0.65)",
                                border=f"1px solid {COLORS['light_border']}",
                                border_radius="14px",
                                width="100%",
                            ),
                            spacing="3",
                            align="start",
                            width="100%",
                        ),
                        padding="0.92rem 0.96rem",
                        background="linear-gradient(180deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.95) 100%)",
                        border=f"1px solid {COLORS['light_border_strong']}",
                        border_radius="18px",
                        width="100%",
                        box_shadow="0 10px 24px rgba(15, 23, 42, 0.05)",
                    ),
                    rx.fragment(),
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            padding="0.82rem 0.88rem",
            background=COLORS["light_panel_alt"],
            border=f"1px solid {COLORS['light_border']}",
            border_radius="16px",
            width="100%",
        ),
        style={
            "padding": "1rem",
            "border": rx.cond(
                card["grid_state"] == "Best Bet",
                "1px solid rgba(15, 159, 110, 0.22)",
                rx.cond(
                    card["grid_state"] == "Positive EV",
                    "1px solid rgba(37, 99, 235, 0.18)",
                    "1px solid rgba(0,0,0,0.05)",
                ),
            ),
            "box_shadow": rx.cond(
                card["grid_state"] == "Best Bet",
                "0 8px 20px rgba(15, 159, 110, 0.10)",
                rx.cond(
                    card["grid_state"] == "Positive EV",
                    "0 6px 16px rgba(37, 99, 235, 0.08)",
                    "0 2px 6px rgba(0,0,0,0.04)",
                ),
            ),
        },
    )
