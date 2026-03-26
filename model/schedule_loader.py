from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests


MATCHUP_COLUMNS = ["away_team", "home_team", "away_pitcher", "home_pitcher"]
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
TEAM_NAME_ALIASES = {
    "Athletics": "Oakland Athletics",
}


def _load_local_matchups(file_path="data/matchups.csv"):
    matchups = pd.read_csv(file_path)

    for column in MATCHUP_COLUMNS:
        if column not in matchups.columns:
            matchups[column] = ""

    return matchups[MATCHUP_COLUMNS].copy()


def _resolve_team_name(team_name):
    if team_name is None or pd.isna(team_name):
        return ""
    return TEAM_NAME_ALIASES.get(str(team_name), str(team_name))


def _load_live_matchups():
    """Load the next upcoming MLB slate from the MLB Stats API."""
    today_local = datetime.now(LOCAL_TIMEZONE).date()
    end_local = today_local + timedelta(days=3)
    response = requests.get(
        SCHEDULE_URL,
        params={
            "sportId": 1,
            "startDate": today_local.isoformat(),
            "endDate": end_local.isoformat(),
            "hydrate": "probablePitcher",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    for day in payload.get("dates", []):
        day_games = []
        for game in day.get("games", []):
            status = game.get("status", {})
            abstract_state = status.get("abstractGameState")
            detailed_state = status.get("detailedState")
            if abstract_state == "Final" or detailed_state == "Final":
                continue

            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            away_team = _resolve_team_name(away.get("team", {}).get("name"))
            home_team = _resolve_team_name(home.get("team", {}).get("name"))
            if not away_team or not home_team:
                continue

            away_pitcher = (
                away.get("probablePitcher", {}).get("fullName")
                or ""
            )
            home_pitcher = (
                home.get("probablePitcher", {}).get("fullName")
                or ""
            )
            day_games.append(
                {
                    "away_team": away_team,
                    "home_team": home_team,
                    "away_pitcher": away_pitcher,
                    "home_pitcher": home_pitcher,
                    "game_date": day.get("date"),
                }
            )

        if day_games:
            return pd.DataFrame(day_games)

    return pd.DataFrame(columns=MATCHUP_COLUMNS + ["game_date"])


def load_today_matchups(data_mode="local"):
    """
    Load today's matchup board with away/home teams and probable starters.

    Returns a dataframe with:
    - away_team
    - home_team
    - away_pitcher
    - home_pitcher
    """

    try:
        if data_mode == "live":
            return _load_live_matchups()

        return _load_local_matchups()
    except Exception:
        return _load_local_matchups()
