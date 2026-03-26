from __future__ import annotations

import reflex as rx

from reflex_app.styles import COLORS, CONTENT_WIDTH, HERO_CARD_STYLE, SECTION_TITLE_STYLE

NAV_ITEMS = [
    ("Dashboard", "/"),
    ("Daily Matchups", "/daily-matchups"),
    ("Drivers", "/drivers"),
    ("Performance", "/performance"),
    ("Season Projections", "/season-projections"),
    ("Settings / About", "/settings"),
]


def top_nav(light: bool = False) -> rx.Component:
    title_color = COLORS["light_text"] if light else COLORS["text"]
    muted_color = COLORS["light_muted"] if light else COLORS["muted"]
    chip_background = COLORS["light_chip"] if light else COLORS["chip"]
    chip_border = COLORS["light_border"] if light else COLORS["border"]
    chip_text = COLORS["light_muted"] if light else COLORS["muted"]
    accent_background = COLORS["light_accent_soft"] if light else COLORS["accent_soft"]
    accent_border = COLORS["light_accent"] if light else COLORS["accent"]
    accent_text = COLORS["light_accent"] if light else COLORS["accent"]
    nav_background = COLORS["light_panel"] if light else COLORS["panel"]
    nav_border = COLORS["light_border"] if light else COLORS["border"]
    nav_hover_background = COLORS["light_panel_alt"] if light else COLORS["chip"]
    nav_hover_border = COLORS["light_border_strong"] if light else COLORS["border_strong"]
    container_style = dict(HERO_CARD_STYLE)
    if light:
        container_style.update(
            {
                "background": "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                "border": f"1px solid {COLORS['light_border']}",
                "box_shadow": "0 10px 28px rgba(15, 23, 42, 0.06)",
            }
        )
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.text("Sportsbook Board", style=SECTION_TITLE_STYLE),
                    rx.heading("MLB Odds & Probability Hub", size="8", color=title_color),
                    rx.text(
                        "Probability-first board design with sportsbook-style hierarchy, sharper cards, and faster matchup scanning.",
                        color=muted_color,
                        font_size="0.89rem",
                        max_width="700px",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.box(
                        "Probability First",
                        padding="0.4rem 0.74rem",
                        border_radius="999px",
                        background=chip_background,
                        border=f"1px solid {chip_border}",
                        color=chip_text,
                        font_size="0.74rem",
                        font_weight="700",
                    ),
                    rx.box(
                        "Market Board",
                        padding="0.4rem 0.74rem",
                        border_radius="999px",
                        background=accent_background,
                        border=f"1px solid {accent_border}",
                        color=accent_text,
                        font_size="0.74rem",
                        font_weight="700",
                    ),
                    spacing="2",
                    flex_wrap="wrap",
                    justify="end",
                ),
                width="100%",
                align="start",
                spacing="4",
            ),
            rx.box(
                rx.hstack(
                    *[
                        rx.link(
                            label,
                            href=route,
                            color=title_color,
                            padding="0.66rem 0.92rem",
                            border_radius="12px",
                            background=nav_background,
                            border=f"1px solid {nav_border}",
                            font_size="0.84rem",
                            font_weight="600",
                            _hover={
                                "background": nav_hover_background,
                                "border": f"1px solid {nav_hover_border}",
                            },
                        )
                        for label, route in NAV_ITEMS
                    ],
                    spacing="2",
                    flex_wrap="wrap",
                    width="100%",
                ),
                width="100%",
                background=COLORS["light_panel_alt"] if light else COLORS["panel_alt"],
                border=f"1px solid {COLORS['light_border']}" if light else f"1px solid {COLORS['border']}",
                border_radius="16px",
                padding="0.5rem",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        max_width=CONTENT_WIDTH,
        margin="0 auto",
        style=container_style,
    )
