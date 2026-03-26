from __future__ import annotations

import reflex as rx

from reflex_app.components.cards import empty_panel, section_header, surface_card
from reflex_app.styles import COLORS, TABLE_SCROLL_STYLE


def simple_table(
    title: str,
    rows: list[dict[str, str]],
    columns: list[str] | None = None,
    helper: str | None = None,
    framed: bool = True,
) -> rx.Component:
    if columns is None:
        columns = []

    table_content = rx.vstack(
        section_header(title, helper),
        rx.cond(
            rows.length() == 0,
            empty_panel(title, "No rows are available for this section yet. Refresh or load more source data."),
            rx.scroll_area(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.foreach(
                                columns,
                                lambda column: rx.table.column_header_cell(
                                    column,
                                    color=COLORS["muted_2"],
                                    font_size="0.72rem",
                                    letter_spacing="0.08em",
                                    text_transform="uppercase",
                                    border_bottom=f"1px solid {COLORS['border_strong']}",
                                    background=COLORS["panel_soft"],
                                    padding="0.82rem 0.9rem",
                                    position="sticky",
                                    top="0",
                                    z_index="1",
                                )
                            )
                        )
                    ),
                    rx.table.body(
                        rx.foreach(
                            rows,
                            lambda row, idx: rx.table.row(
                                rx.foreach(
                                    columns,
                                    lambda column: rx.table.cell(
                                        row[column],
                                        padding="0.78rem 0.9rem",
                                        font_size="0.84rem",
                                        color=COLORS["text"],
                                        border_bottom=f"1px solid {COLORS['border']}",
                                        white_space="nowrap",
                                    )
                                ),
                                background=rx.cond(idx % 2 == 0, COLORS["panel"], COLORS["row_alt"]),
                            )
                        )
                    ),
                    variant="surface",
                    size="2",
                    width="100%",
                    min_width=rx.breakpoints(initial="880px", lg="100%"),
                ),
                type="always",
                scrollbars="horizontal",
                style=TABLE_SCROLL_STYLE,
            ),
        ),
        spacing="3",
        align="start",
        width="100%",
    )
    if framed:
        return surface_card(table_content)
    return table_content


def light_table(
    title: str,
    rows: list[dict[str, str]],
    columns: list[str] | None = None,
    helper: str | None = None,
) -> rx.Component:
    if columns is None:
        columns = []

    return rx.box(
        rx.vstack(
            rx.vstack(
                rx.text("Supporting Detail", font_size="0.72rem", letter_spacing="0.14em", text_transform="uppercase", color=COLORS["light_muted_2"], font_weight="700"),
                rx.text(title, font_size="1.08rem", font_weight="900", color=COLORS["light_text"], letter_spacing="-0.02em"),
                rx.cond(
                    helper is None,
                    rx.fragment(),
                    rx.text(helper, font_size="0.84rem", color=COLORS["light_muted"], line_height="1.48"),
                ),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.cond(
                rows.length() == 0,
                rx.box(
                    rx.text("No rows available for the current filter set.", font_size="0.86rem", color=COLORS["light_muted"]),
                    width="100%",
                    padding="0.85rem 0.95rem",
                    background=COLORS["light_panel_alt"],
                    border=f"1px solid {COLORS['light_border']}",
                    border_radius="16px",
                ),
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.foreach(
                                    columns,
                                    lambda column: rx.table.column_header_cell(
                                        column,
                                        color=COLORS["light_muted_2"],
                                        font_size="0.72rem",
                                        letter_spacing="0.08em",
                                        text_transform="uppercase",
                                        border_bottom="1px solid rgba(15, 23, 42, 0.06)",
                                        background=COLORS["light_panel_alt"],
                                        padding="0.74rem 0.82rem",
                                        position="sticky",
                                        top="0",
                                        z_index="1",
                                    ),
                                )
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                rows,
                                lambda row, idx: rx.table.row(
                                    rx.foreach(
                                        columns,
                                        lambda column: rx.table.cell(
                                            row[column],
                                            padding="0.92rem 0.82rem",
                                            font_size=rx.cond(column == "Rank", "0.92rem", rx.cond(column == "Team", "0.93rem", "0.81rem")),
                                            font_weight=rx.cond(column == "Rank", "900", rx.cond(column == "Team", "800", "600")),
                                            color=rx.cond(
                                                column == "Rank",
                                                COLORS["light_accent"],
                                                rx.cond(column == "Team", COLORS["light_text"], rx.cond(column == "Win %", COLORS["light_muted_2"], COLORS["light_muted"])),
                                            ),
                                            border_bottom="1px solid rgba(15, 23, 42, 0.04)",
                                            white_space="nowrap",
                                        ),
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
                        min_width=rx.breakpoints(initial="980px", lg="100%"),
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
                ),
            ),
            spacing="2",
            align="start",
            width="100%",
        ),
        width="100%",
        padding="0.95rem",
        background=COLORS["light_panel"],
        border=f"1px solid {COLORS['light_border']}",
        border_radius="22px",
        box_shadow="0 10px 24px rgba(15, 23, 42, 0.05)",
    )
