from __future__ import annotations

import reflex as rx

from reflex_app.pages.daily_matchups import daily_matchups_page
from reflex_app.pages.dashboard import dashboard_page
from reflex_app.pages.drivers import drivers_page
from reflex_app.pages.performance import performance_page
from reflex_app.pages.projections import projections_page
from reflex_app.pages.settings import settings_page
from reflex_app.services.startup_checks import run_startup_checks
from reflex_app.styles import COLORS

run_startup_checks()


app = rx.App(
    theme=rx.theme(
        appearance="dark",
        accent_color="blue",
        gray_color="slate",
        radius="large",
    ),
    style={
        "font_family": "'Inter', 'Avenir Next', 'Segoe UI', sans-serif",
        "background_color": COLORS["bg"],
        "color": COLORS["text"],
    },
)

app.add_page(dashboard_page, route="/", title="MLB Dashboard")
app.add_page(daily_matchups_page, route="/daily-matchups", title="Daily Matchups")
app.add_page(drivers_page, route="/drivers", title="Drivers")
app.add_page(performance_page, route="/performance", title="Performance")
app.add_page(projections_page, route="/season-projections", title="Season Projections")
app.add_page(settings_page, route="/settings", title="Settings / About")
