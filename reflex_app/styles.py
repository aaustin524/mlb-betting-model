"""Shared sportsbook-style design tokens for the Reflex analytics dashboard."""

from __future__ import annotations


COLORS = {
    "bg": "#07111f",
    "bg_alt": "#0b1728",
    "shell": "#0d1b2f",
    "panel": "#102033",
    "panel_alt": "#12263d",
    "panel_soft": "#16304b",
    "chip": "#132a44",
    "chip_alt": "#173451",
    "row_alt": "#11253a",
    "border": "rgba(148, 163, 184, 0.12)",
    "border_strong": "rgba(148, 163, 184, 0.24)",
    "text": "#F8FAFC",
    "muted": "#B6C2D2",
    "muted_2": "#8EA3BA",
    "accent": "#1E78FF",
    "accent_soft": "rgba(30, 120, 255, 0.16)",
    "success": "#22C55E",
    "success_soft": "rgba(34, 197, 94, 0.14)",
    "danger": "#F43F5E",
    "danger_soft": "rgba(244, 63, 94, 0.14)",
    "info": "#38BDF8",
    "info_soft": "rgba(56, 189, 248, 0.14)",
    "light_canvas": "#f4f7fb",
    "light_panel": "#ffffff",
    "light_panel_alt": "#f8fafc",
    "light_chip": "#eef4ff",
    "light_border": "rgba(15, 23, 42, 0.08)",
    "light_border_strong": "rgba(15, 23, 42, 0.14)",
    "light_text": "#0f172a",
    "light_muted": "#5b6b81",
    "light_muted_2": "#7b8ba1",
    "light_accent": "#2563eb",
    "light_accent_soft": "rgba(37, 99, 235, 0.10)",
    "light_success": "#0f9f6e",
    "light_success_soft": "rgba(15, 159, 110, 0.10)",
}

CONTENT_WIDTH = "1320px"
SHELL_GUTTER = "1.35rem"
SECTION_GAP = "1rem"

PAGE_STYLE = {
    "min_height": "100vh",
    "background": (
        "radial-gradient(circle at top left, rgba(30, 120, 255, 0.16), transparent 24%),"
        " radial-gradient(circle at top right, rgba(56, 189, 248, 0.10), transparent 20%),"
        " linear-gradient(180deg, #07111f 0%, #081423 48%, #07111f 100%)"
    ),
    "color": COLORS["text"],
}

CARD_STYLE = {
    "background": COLORS["panel"],
    "border": f"1px solid {COLORS['border']}",
    "border_radius": "18px",
    "padding": "1.05rem",
    "box_shadow": "0 16px 42px rgba(2, 8, 23, 0.34)",
}

SOFT_CARD_STYLE = {
    "background": COLORS["panel_alt"],
    "border": f"1px solid {COLORS['border']}",
    "border_radius": "18px",
    "padding": "1rem",
}

HERO_CARD_STYLE = {
    "background": "linear-gradient(180deg, rgba(16,32,51,0.96) 0%, rgba(12,27,44,0.98) 100%)",
    "border": f"1px solid {COLORS['border']}",
    "border_radius": "24px",
    "padding": "1.2rem 1.3rem",
    "box_shadow": "0 18px 48px rgba(2, 8, 23, 0.38)",
}

PAGE_HEADER_STYLE = {
    "background": "linear-gradient(180deg, rgba(18,38,61,0.96) 0%, rgba(14,31,49,0.98) 100%)",
    "border": f"1px solid {COLORS['border']}",
    "border_radius": "20px",
    "padding": "1.05rem 1.15rem",
    "box_shadow": "0 14px 34px rgba(2, 8, 23, 0.28)",
}

SECTION_TITLE_STYLE = {
    "font_size": "0.72rem",
    "letter_spacing": "0.15em",
    "text_transform": "uppercase",
    "color": COLORS["muted_2"],
    "font_weight": "700",
}

SECTION_SUBTITLE_STYLE = {
    "font_size": "0.88rem",
    "color": COLORS["muted"],
    "line_height": "1.45",
}

TABLE_SCROLL_STYLE = {
    "width": "100%",
    "border_radius": "16px",
    "border": f"1px solid {COLORS['border']}",
    "background": COLORS["panel"],
    "overflow": "hidden",
    "max_width": "100%",
}

CONTROL_STYLE = {
    "background": COLORS["panel"],
    "border": f"1px solid {COLORS['border_strong']}",
    "color": COLORS["text"],
    "border_radius": "12px",
    "height": "42px",
    "padding": "0 0.8rem",
    "box_shadow": "none",
    "_focus": {
        "border": f"1px solid {COLORS['accent']}",
        "box_shadow": "0 0 0 3px rgba(30, 120, 255, 0.18)",
    },
}
