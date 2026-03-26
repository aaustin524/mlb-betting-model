from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import loading_panel
from reflex_app.components.header import top_nav
from reflex_app.state.app_state import AppState
from reflex_app.styles import COLORS, CONTENT_WIDTH, PAGE_HEADER_STYLE, PAGE_STYLE, SECTION_TITLE_STYLE, SHELL_GUTTER


def page_shell(title: str, subtitle: str, *children: rx.Component, light: bool = False) -> rx.Component:
    page_style = dict(PAGE_STYLE)
    page_header_style = dict(PAGE_HEADER_STYLE)
    title_color = COLORS["light_text"] if light else COLORS["text"]
    muted_color = COLORS["light_muted"] if light else COLORS["muted"]
    chip_background = COLORS["light_chip"] if light else COLORS["chip"]
    chip_border = COLORS["light_border"] if light else COLORS["border"]
    chip_text = COLORS["light_muted"] if light else COLORS["muted"]
    if light:
        page_style.update(
            {
                "background": "linear-gradient(180deg, #f6f8fc 0%, #f2f5fa 50%, #f7f9fc 100%)",
                "color": COLORS["light_text"],
            }
        )
        page_header_style.update(
            {
                "background": "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)",
                "border": f"1px solid {COLORS['light_border']}",
                "box_shadow": "0 10px 26px rgba(15, 23, 42, 0.05)",
            }
        )
    return rx.box(
        rx.vstack(
            top_nav(light=light),
            rx.box(
                rx.hstack(
                    rx.vstack(
                        rx.text("Workspace", style=SECTION_TITLE_STYLE),
                        rx.text(title, font_size=rx.breakpoints(initial="1.55rem", md="1.9rem"), font_weight="800", color=title_color),
                        rx.text(
                            subtitle,
                            color=muted_color,
                            max_width="720px",
                            font_size="0.92rem",
                            line_height="1.45",
                        ),
                        spacing="1",
                        align="start",
                    ),
                    rx.spacer(),
                    rx.box(
                        "Shared model services",
                        padding="0.42rem 0.78rem",
                        border_radius="999px",
                        background=chip_background,
                        border=f"1px solid {chip_border}",
                        color=chip_text,
                        font_size="0.75rem",
                        font_weight="700",
                        white_space="nowrap",
                    ),
                    width="100%",
                    align="start",
                    spacing="4",
                    flex_wrap="wrap",
                ),
                width="100%",
                style=page_header_style,
            ),
            rx.cond(
                AppState.is_loading,
                loading_panel(),
                rx.vstack(*children, spacing="5", width="100%"),
            ),
            max_width=CONTENT_WIDTH,
            margin="0 auto",
            padding=SHELL_GUTTER,
            spacing="5",
            align="start",
            width="100%",
        ),
        style=page_style,
        width="100%",
        on_mount=AppState.load,
    )
