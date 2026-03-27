"""Season Monitor leaderboard and standings rendering helpers."""

from __future__ import annotations

import math
import sqlite3
from html import escape
from textwrap import dedent

import numpy as np
import pandas as pd
import streamlit as st

try:
    from utils.streamlit_compat import cache_data_if_runtime
except ModuleNotFoundError:
    from app.utils.streamlit_compat import cache_data_if_runtime
from model.bullpen_usage import estimate_bullpen_fatigue, load_recent_bullpen_usage
from model.lineup_strength import calculate_lineup_adjustment
from model.rolling_team_ratings import MLB_TEAM_ID_TO_NAME
from project_config import (
    DB_PATH,
    LEAN_BET_EDGE_THRESHOLD,
    LEAN_BET_EV_THRESHOLD,
    STRONG_BET_EDGE_THRESHOLD,
    STRONG_BET_EV_THRESHOLD,
)

SEASON_PROJECTION_SPREAD = 1.0
SEASON_WIN_PCT_MIN = 0.350
SEASON_WIN_PCT_MAX = 0.650
HOME_FIELD_LOGIT_EDGE = math.log(0.54 / 0.46)
TEAM_NAME_ALIASES = {
    "athletics": "Oakland Athletics",
}
TEAM_TO_DIVISION = {
    "Baltimore Orioles": "AL East",
    "Boston Red Sox": "AL East",
    "New York Yankees": "AL East",
    "Tampa Bay Rays": "AL East",
    "Toronto Blue Jays": "AL East",
    "Chicago White Sox": "AL Central",
    "Cleveland Guardians": "AL Central",
    "Detroit Tigers": "AL Central",
    "Kansas City Royals": "AL Central",
    "Minnesota Twins": "AL Central",
    "Houston Astros": "AL West",
    "Los Angeles Angels": "AL West",
    "Oakland Athletics": "AL West",
    "Seattle Mariners": "AL West",
    "Texas Rangers": "AL West",
    "Atlanta Braves": "NL East",
    "Miami Marlins": "NL East",
    "New York Mets": "NL East",
    "Philadelphia Phillies": "NL East",
    "Washington Nationals": "NL East",
    "Chicago Cubs": "NL Central",
    "Cincinnati Reds": "NL Central",
    "Milwaukee Brewers": "NL Central",
    "Pittsburgh Pirates": "NL Central",
    "St. Louis Cardinals": "NL Central",
    "Arizona Diamondbacks": "NL West",
    "Colorado Rockies": "NL West",
    "Los Angeles Dodgers": "NL West",
    "San Diego Padres": "NL West",
    "San Francisco Giants": "NL West",
}
DIVISION_ORDER = [
    "AL East",
    "AL Central",
    "AL West",
    "NL East",
    "NL Central",
    "NL West",
]
LEAGUE_ORDER = ["AL", "NL"]
PLAYOFF_ODDS_SIMS = 3000
PLAYOFF_ODDS_SEED = 20260316
STANDINGS_FILTER_OPTIONS = ["All", "AL", "NL"] + DIVISION_ORDER
SEASON_MONITOR_LEAGUE_OPTIONS = ["MLB", "AL", "NL"]
SEASON_MONITOR_TABLE_OPTIONS = ["Top 10", "Top 25", "All"]


def _normalize_team_name(team_name):
    if team_name is None or pd.isna(team_name):
        return ""

    normalized = str(team_name).strip().lower()
    for old_value, new_value in {
        ".": "",
        ",": "",
        "'": "",
        "-": " ",
    }.items():
        normalized = normalized.replace(old_value, new_value)

    return " ".join(token for token in normalized.split() if token not in {"the"})


def _resolve_team_name(team_name):
    normalized_name = _normalize_team_name(team_name)
    return TEAM_NAME_ALIASES.get(normalized_name, team_name)


@cache_data_if_runtime(show_spinner=False)
def load_schedule_template_from_db(db_path=DB_PATH):
    """Load the latest full MLB season schedule from SQLite for season projections."""
    query = """
        SELECT
            season,
            game_date,
            home_team_id,
            away_team_id
        FROM games
        ORDER BY season DESC, game_date, game_id
    """

    with sqlite3.connect(db_path) as connection:
        games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return pd.DataFrame(columns=["season", "game_date", "home_team", "away_team"])

    latest_season = int(games_df["season"].max())
    schedule_df = games_df.loc[games_df["season"] == latest_season].copy()
    if schedule_df.empty:
        return pd.DataFrame(columns=["season", "game_date", "home_team", "away_team"])

    schedule_df["home_team"] = schedule_df["home_team_id"].map(MLB_TEAM_ID_TO_NAME)
    schedule_df["away_team"] = schedule_df["away_team_id"].map(MLB_TEAM_ID_TO_NAME)
    schedule_df["home_team"] = schedule_df["home_team"].map(_resolve_team_name)
    schedule_df["away_team"] = schedule_df["away_team"].map(_resolve_team_name)
    schedule_df = schedule_df.dropna(subset=["home_team", "away_team"]).copy()

    return schedule_df[["season", "game_date", "home_team", "away_team"]]


@cache_data_if_runtime(show_spinner=False)
def load_current_season_schedule_from_db(db_path=DB_PATH):
    """Load the latest season schedule from SQLite, including unplayed games when present."""
    query = """
        SELECT
            season,
            game_date,
            home_team_id,
            away_team_id,
            home_score,
            away_score,
            status
        FROM games
        ORDER BY season DESC, game_date, game_id
    """

    with sqlite3.connect(db_path) as connection:
        games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return pd.DataFrame(
            columns=[
                "season",
                "game_date",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "status",
            ]
        )

    latest_season = int(games_df["season"].max())
    schedule_df = games_df.loc[games_df["season"] == latest_season].copy()
    schedule_df["home_team"] = schedule_df["home_team_id"].map(MLB_TEAM_ID_TO_NAME)
    schedule_df["away_team"] = schedule_df["away_team_id"].map(MLB_TEAM_ID_TO_NAME)
    schedule_df["home_team"] = schedule_df["home_team"].map(_resolve_team_name)
    schedule_df["away_team"] = schedule_df["away_team"].map(_resolve_team_name)
    schedule_df = schedule_df.dropna(subset=["home_team", "away_team"]).copy()
    schedule_df["game_date"] = pd.to_datetime(schedule_df["game_date"], errors="coerce")

    # When the local database contains spring or exhibition rows before the
    # current regular-season slate, anchor the standings window to the first
    # scheduled regular-season date minus one day so current records start at
    # Opening Day instead of earlier exhibition results.
    scheduled_rows = schedule_df.loc[schedule_df["status"].fillna("").eq("Scheduled")].copy()
    if not scheduled_rows.empty:
        regular_season_start = scheduled_rows["game_date"].min() - pd.Timedelta(days=1)
        schedule_df = schedule_df.loc[schedule_df["game_date"] >= regular_season_start].copy()

    return schedule_df[
        [
            "season",
            "game_date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "status",
        ]
    ]


def _build_talent_table(team_ratings_df):
    standings_df = team_ratings_df.reset_index().rename(columns={"team": "Team"}).copy()
    standings_df["Offense Score"] = (
        standings_df["offense_vs_rhp"] + standings_df["offense_vs_lhp"]
    ) / 2.0
    standings_df["Pitching Score"] = 1.0 / standings_df["pitching"]
    standings_df["Bullpen Score"] = 1.0 / standings_df["bullpen"]

    standings_df["Power Score"] = (
        (standings_df["Offense Score"] * 0.50)
        + (standings_df["Pitching Score"] * 0.30)
        + (standings_df["Bullpen Score"] * 0.20)
    )

    average_power_score = standings_df["Power Score"].mean()
    power_delta = standings_df["Power Score"] - average_power_score
    standings_df["Talent Win %"] = (0.500 + (power_delta * SEASON_PROJECTION_SPREAD)).clip(
        lower=SEASON_WIN_PCT_MIN,
        upper=SEASON_WIN_PCT_MAX,
    )
    return standings_df


def _logit(probability):
    return math.log(probability / (1.0 - probability))


def _sigmoid(value):
    return 1.0 / (1.0 + math.exp(-value))


def _project_schedule_based_wins(standings_df, schedule_df):
    team_lookup = standings_df.set_index("Team")["Talent Win %"].to_dict()
    valid_schedule = schedule_df[
        schedule_df["home_team"].isin(team_lookup) & schedule_df["away_team"].isin(team_lookup)
    ].copy()
    if valid_schedule.empty:
        return None

    projected_wins = {team_name: 0.0 for team_name in team_lookup}
    games_played = {team_name: 0 for team_name in team_lookup}

    for game_row in valid_schedule.itertuples(index=False):
        home_talent = float(team_lookup[game_row.home_team])
        away_talent = float(team_lookup[game_row.away_team])
        home_win_prob = _sigmoid(_logit(home_talent) - _logit(away_talent) + HOME_FIELD_LOGIT_EDGE)

        projected_wins[game_row.home_team] += home_win_prob
        projected_wins[game_row.away_team] += 1.0 - home_win_prob
        games_played[game_row.home_team] += 1
        games_played[game_row.away_team] += 1

    projected_wins_df = pd.DataFrame(
        {
            "Team": list(projected_wins.keys()),
            "Projected Wins": list(projected_wins.values()),
            "Schedule Games": [games_played[team_name] for team_name in projected_wins],
        }
    )
    projected_wins_df["Projected Win %"] = projected_wins_df["Projected Wins"] / projected_wins_df["Schedule Games"]

    # If the latest historical season is missing a few games, normalize back to
    # a 162-game equivalent so the standings remain easier to compare.
    needs_rescale = projected_wins_df["Schedule Games"].nunique() > 1 or projected_wins_df["Schedule Games"].iat[0] != 162
    if needs_rescale:
        projected_wins_df["Projected Wins"] = projected_wins_df["Projected Win %"] * 162.0

    return projected_wins_df[["Team", "Projected Win %", "Projected Wins"]]


def build_current_division_standings(team_ratings_df):
    """Build current division standings with actual and projected records."""
    if team_ratings_df is None or team_ratings_df.empty:
        return pd.DataFrame()

    season_games_df = load_current_season_schedule_from_db()
    if season_games_df.empty:
        return pd.DataFrame()

    talent_df = _build_talent_table(team_ratings_df)
    team_lookup = talent_df.set_index("Team")["Talent Win %"].to_dict()

    completed_games_df = season_games_df.dropna(subset=["home_score", "away_score"]).copy()
    remaining_games_df = season_games_df.loc[season_games_df["home_score"].isna() | season_games_df["away_score"].isna()].copy()

    actual_records = {
        team_name: {
            "Actual Wins": 0,
            "Actual Losses": 0,
            "Games Played": 0,
        }
        for team_name in team_lookup
    }

    for game_row in completed_games_df.itertuples(index=False):
        home_team = game_row.home_team
        away_team = game_row.away_team
        if home_team not in actual_records or away_team not in actual_records:
            continue

        home_score = float(game_row.home_score)
        away_score = float(game_row.away_score)
        actual_records[home_team]["Games Played"] += 1
        actual_records[away_team]["Games Played"] += 1
        if home_score > away_score:
            actual_records[home_team]["Actual Wins"] += 1
            actual_records[away_team]["Actual Losses"] += 1
        elif away_score > home_score:
            actual_records[away_team]["Actual Wins"] += 1
            actual_records[home_team]["Actual Losses"] += 1

    projected_remaining = {team_name: 0.0 for team_name in team_lookup}
    remaining_games = {team_name: 0 for team_name in team_lookup}

    for game_row in remaining_games_df.itertuples(index=False):
        home_team = game_row.home_team
        away_team = game_row.away_team
        if home_team not in team_lookup or away_team not in team_lookup:
            continue

        home_talent = float(team_lookup[home_team])
        away_talent = float(team_lookup[away_team])
        home_win_prob = _sigmoid(_logit(home_talent) - _logit(away_talent) + HOME_FIELD_LOGIT_EDGE)

        projected_remaining[home_team] += home_win_prob
        projected_remaining[away_team] += 1.0 - home_win_prob
        remaining_games[home_team] += 1
        remaining_games[away_team] += 1

    standings_df = talent_df[["Team", "Power Score", "Offense Score", "Pitching Score", "Bullpen Score"]].copy()
    standings_df["Division"] = standings_df["Team"].map(TEAM_TO_DIVISION).fillna("Other")
    standings_df["Actual Wins"] = standings_df["Team"].map(lambda team_name: actual_records[team_name]["Actual Wins"])
    standings_df["Actual Losses"] = standings_df["Team"].map(lambda team_name: actual_records[team_name]["Actual Losses"])
    standings_df["Games Played"] = standings_df["Team"].map(lambda team_name: actual_records[team_name]["Games Played"])
    standings_df["Remaining Games"] = standings_df["Team"].map(lambda team_name: remaining_games[team_name])
    standings_df["Proj Remaining Wins"] = standings_df["Team"].map(lambda team_name: projected_remaining[team_name])
    standings_df["Proj Remaining Losses"] = standings_df["Remaining Games"] - standings_df["Proj Remaining Wins"]
    standings_df["Projected Wins"] = standings_df["Actual Wins"] + standings_df["Proj Remaining Wins"]
    standings_df["Projected Losses"] = standings_df["Actual Losses"] + standings_df["Proj Remaining Losses"]
    games_played = pd.to_numeric(standings_df["Games Played"], errors="coerce")
    actual_wins = pd.to_numeric(standings_df["Actual Wins"], errors="coerce")
    projected_wins = pd.to_numeric(standings_df["Projected Wins"], errors="coerce")
    projected_losses = pd.to_numeric(standings_df["Projected Losses"], errors="coerce")

    standings_df["Win %"] = actual_wins.div(games_played.where(games_played != 0)).fillna(0.0)
    total_games_projection = (projected_wins + projected_losses)
    standings_df["Projected Win %"] = projected_wins.div(
        total_games_projection.where(total_games_projection != 0)
    ).fillna(0.0)
    standings_df["League"] = standings_df["Division"].str[:2]
    standings_df = standings_df.sort_values(
        by=["Division", "Projected Wins", "Power Score"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    standings_df["Division Rank"] = standings_df.groupby("Division").cumcount() + 1
    standings_df["League Rank"] = (
        standings_df.sort_values(
            by=["League", "Projected Wins", "Power Score"],
            ascending=[True, False, False],
        )
        .groupby("League")
        .cumcount()
        .add(1)
        .reindex(standings_df.sort_values(by=["League", "Projected Wins", "Power Score"], ascending=[True, False, False]).index)
    )
    standings_df["League Rank"] = standings_df["League Rank"].fillna(0).astype(int)

    wildcard_df = standings_df.loc[standings_df["Division Rank"] > 1].copy()
    if not wildcard_df.empty:
        wildcard_df = wildcard_df.sort_values(
            by=["League", "Projected Wins", "Power Score"],
            ascending=[True, False, False],
        ).reset_index(drop=True)
        wildcard_df["Wildcard Rank"] = wildcard_df.groupby("League").cumcount() + 1
        standings_df = standings_df.merge(
            wildcard_df[["Team", "Wildcard Rank"]],
            on="Team",
            how="left",
        )
    else:
        standings_df["Wildcard Rank"] = pd.NA

    standings_df["Projected Wins"] = standings_df["Projected Wins"].round(1)
    standings_df["Projected Losses"] = standings_df["Projected Losses"].round(1)
    standings_df["Proj Remaining Wins"] = standings_df["Proj Remaining Wins"].round(1)
    standings_df["Proj Remaining Losses"] = standings_df["Proj Remaining Losses"].round(1)
    standings_df["Playoff Outlook"] = standings_df.apply(_build_playoff_outlook, axis=1)
    return standings_df


def _build_playoff_outlook(row):
    if int(row["Division Rank"]) == 1:
        return "Division Leader"

    wildcard_rank = row.get("Wildcard Rank")
    if pd.isna(wildcard_rank):
        return "Outside"

    wildcard_rank = int(wildcard_rank)
    if wildcard_rank <= 3:
        return "Wild Card"
    if wildcard_rank <= 6:
        return "Bubble"
    return "Outside"


def build_wildcard_standings(standings_df):
    if standings_df is None or standings_df.empty:
        return pd.DataFrame()

    wildcard_df = standings_df.loc[standings_df["Division Rank"] > 1].copy()
    if wildcard_df.empty:
        return wildcard_df

    wildcard_df = wildcard_df.sort_values(
        by=["League", "Projected Wins", "Power Score"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    wildcard_df["Wildcard Rank"] = wildcard_df.groupby("League").cumcount() + 1
    cutoff_lookup = (
        wildcard_df.loc[wildcard_df["Wildcard Rank"] == 3, ["League", "Projected Wins"]]
        .rename(columns={"Projected Wins": "Wildcard Cutline"})
        .set_index("League")["Wildcard Cutline"]
        .to_dict()
    )
    wildcard_df["Wildcard Cutline"] = wildcard_df["League"].map(cutoff_lookup)
    wildcard_df["Games Behind Cutline"] = (
        wildcard_df["Wildcard Cutline"] - wildcard_df["Projected Wins"]
    ).round(1)
    wildcard_df.loc[wildcard_df["Wildcard Rank"] <= 3, "Games Behind Cutline"] = 0.0
    return wildcard_df


def _build_cutline_trend(row):
    wildcard_rank = int(row["Wildcard Rank"])
    playoff_odds = float(row.get("Playoff Odds", 0.0) or 0.0)
    games_back = float(row.get("Games Behind Cutline", 0.0) or 0.0)

    if wildcard_rank <= 3 and playoff_odds >= 60.0:
        return "IN"
    if games_back <= 2.0 or playoff_odds >= 20.0:
        return "WATCH"
    return "BACK"


def build_playoff_outlook_summary(standings_df, wildcard_df):
    if standings_df is None or standings_df.empty:
        return None

    division_leaders_df = standings_df.loc[standings_df["Division Rank"] == 1].copy()
    wildcard_leaders_df = wildcard_df.loc[wildcard_df["Wildcard Rank"] <= 3].copy() if not wildcard_df.empty else pd.DataFrame()
    bubble_df = wildcard_df.loc[wildcard_df["Wildcard Rank"].isin([4, 5])].copy() if not wildcard_df.empty else pd.DataFrame()

    return {
        "division_leaders": division_leaders_df.sort_values(
            by=["League", "Projected Wins", "Power Score"],
            ascending=[True, False, False],
        ),
        "wildcard_leaders": wildcard_leaders_df.sort_values(
            by=["League", "Projected Wins", "Power Score"],
            ascending=[True, False, False],
        ),
        "bubble_teams": bubble_df.sort_values(
            by=["League", "Projected Wins", "Power Score"],
            ascending=[True, False, False],
        ),
    }


def _build_remaining_schedule_with_probs(team_ratings_df):
    talent_df = _build_talent_table(team_ratings_df)
    team_lookup = talent_df.set_index("Team")["Talent Win %"].to_dict()
    season_games_df = load_current_season_schedule_from_db()
    if season_games_df.empty:
        return pd.DataFrame(columns=["home_team", "away_team", "home_win_prob"])

    remaining_games_df = season_games_df.loc[
        season_games_df["home_score"].isna() | season_games_df["away_score"].isna()
    ].copy()
    remaining_games_df = remaining_games_df[
        remaining_games_df["home_team"].isin(team_lookup) & remaining_games_df["away_team"].isin(team_lookup)
    ].copy()
    if remaining_games_df.empty:
        return pd.DataFrame(columns=["home_team", "away_team", "home_win_prob"])

    remaining_games_df["home_win_prob"] = remaining_games_df.apply(
        lambda row: _sigmoid(
            _logit(float(team_lookup[row["home_team"]]))
            - _logit(float(team_lookup[row["away_team"]]))
            + HOME_FIELD_LOGIT_EDGE
        ),
        axis=1,
    )
    return remaining_games_df[["home_team", "away_team", "home_win_prob"]]


@cache_data_if_runtime(show_spinner=False)
def simulate_playoff_odds(team_ratings_df, sims=PLAYOFF_ODDS_SIMS, seed=PLAYOFF_ODDS_SEED):
    """Estimate division, wildcard, and playoff odds by simulating remaining games."""
    standings_df = build_current_division_standings(team_ratings_df)
    if standings_df.empty:
        return pd.DataFrame()

    remaining_games_df = _build_remaining_schedule_with_probs(team_ratings_df)
    teams_df = standings_df[["Team", "Division", "League", "Power Score", "Actual Wins"]].copy().reset_index(drop=True)
    teams_df["team_index"] = teams_df.index

    base_wins = teams_df["Actual Wins"].to_numpy(dtype=float)
    power_eps = teams_df["Power Score"].to_numpy(dtype=float) * 1e-6
    wins_matrix = np.repeat(base_wins[:, None], sims, axis=1)

    if not remaining_games_df.empty:
        team_index_lookup = teams_df.set_index("Team")["team_index"].to_dict()
        home_indices = remaining_games_df["home_team"].map(team_index_lookup).to_numpy(dtype=int)
        away_indices = remaining_games_df["away_team"].map(team_index_lookup).to_numpy(dtype=int)
        home_probs = remaining_games_df["home_win_prob"].to_numpy(dtype=float)

        rng = np.random.default_rng(seed)
        home_results = rng.random((len(remaining_games_df), sims)) < home_probs[:, None]

        for game_idx in range(len(remaining_games_df)):
            home_wins = home_results[game_idx].astype(float)
            wins_matrix[home_indices[game_idx], :] += home_wins
            wins_matrix[away_indices[game_idx], :] += 1.0 - home_wins

    division_titles = np.zeros_like(wins_matrix, dtype=bool)
    wildcard_berths = np.zeros_like(wins_matrix, dtype=bool)

    for division_name in DIVISION_ORDER:
        division_indices = teams_df.index[teams_df["Division"] == division_name].to_numpy(dtype=int)
        if len(division_indices) == 0:
            continue
        division_scores = wins_matrix[division_indices, :] + power_eps[division_indices][:, None]
        winner_rows = np.argmax(division_scores, axis=0)
        division_titles[division_indices[winner_rows], np.arange(sims)] = True

    for league_name in LEAGUE_ORDER:
        league_indices = teams_df.index[teams_df["League"] == league_name].to_numpy(dtype=int)
        if len(league_indices) == 0:
            continue

        non_division_mask = ~division_titles[league_indices, :]
        league_scores = wins_matrix[league_indices, :] + power_eps[league_indices][:, None]
        eligible_scores = np.where(non_division_mask, league_scores, -np.inf)
        top_k = min(3, len(league_indices))
        if top_k <= 0:
            continue
        top_rows = np.argpartition(eligible_scores, -top_k, axis=0)[-top_k:, :]
        for sim_idx in range(sims):
            wildcard_berths[league_indices[top_rows[:, sim_idx]], sim_idx] = True

    playoff_berths = division_titles | wildcard_berths
    odds_df = teams_df[["Team"]].copy()
    odds_df["Division Odds"] = np.round(division_titles.mean(axis=1) * 100.0, 1)
    odds_df["Wildcard Odds"] = np.round(wildcard_berths.mean(axis=1) * 100.0, 1)
    odds_df["Playoff Odds"] = np.round(playoff_berths.mean(axis=1) * 100.0, 1)
    return odds_df


def build_projected_standings(team_ratings_df):
    """
    Build a projected standings table from current team ratings.

    The primary path uses the latest full MLB season schedule stored in SQLite
    as a template, converts team ratings into talent win rates, then sums game-
    level expected wins with a small home-field edge. If schedule data is not
    available, the function falls back to the older direct 162-game heuristic.
    """
    if team_ratings_df is None or team_ratings_df.empty:
        return pd.DataFrame()

    standings_df = _build_talent_table(team_ratings_df)
    schedule_df = load_schedule_template_from_db()
    schedule_projection_df = _project_schedule_based_wins(standings_df, schedule_df)
    if schedule_projection_df is not None:
        standings_df = standings_df.merge(schedule_projection_df, on="Team", how="left")
    else:
        standings_df["Projected Win %"] = standings_df["Talent Win %"]
        standings_df["Projected Wins"] = standings_df["Projected Win %"] * 162.0

    standings_df = standings_df[
        [
            "Team",
            "Power Score",
            "Projected Win %",
            "Projected Wins",
            "Offense Score",
            "Pitching Score",
            "Bullpen Score",
        ]
    ].sort_values(by=["Projected Wins", "Power Score"], ascending=[False, False]).reset_index(drop=True)
    standings_df.index = standings_df.index + 1
    standings_df = standings_df.reset_index().rename(columns={"index": "Rank"})

    return standings_df


def _add_rank_column(dataframe):
    ranked_df = dataframe.reset_index(drop=True).copy()
    ranked_df.index = ranked_df.index + 1
    return ranked_df.reset_index().rename(columns={"index": "Rank"})


def _render_monitor_section_header(title, subtitle=None):
    st.markdown(f'<div class="section-label">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def _format_driver_decimal(value, digits=2, signed=False):
    if value is None or pd.isna(value):
        return "N/A"
    numeric_value = float(value)
    prefix = "+" if signed and numeric_value > 0 else ""
    return f"{prefix}{numeric_value:.{digits}f}"


def _format_driver_hand(value):
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "N/A"
    return str(value).strip().upper()


def _get_pitcher_tier(rank_value):
    if int(rank_value) == 1:
        return "Elite"
    if int(rank_value) <= 3:
        return "Strong"
    return "Solid"


def _get_bullpen_display_status(value):
    status_map = {
        "Fresh": "Fresh",
        "Stable": "Stable",
        "Watch": "Elevated",
        "Stressed": "At Risk",
    }
    return status_map.get(str(value), str(value))


def _get_model_profile_tone(value):
    tone_map = {
        "Offense Driven": "profile-offense",
        "Pitching Led": "profile-pitching",
        "Bullpen Led": "profile-bullpen",
        "Balanced": "profile-balanced",
    }
    return tone_map.get(str(value), "profile-balanced")


def _get_driver_note(metric_type, row):
    if metric_type == "starter":
        edge_value = float(row["Starter Edge"])
        if edge_value >= 0.5:
            return "Clear SP advantage"
        if edge_value >= 0.3:
            return "Meaningful mound edge"
        return "Moderate starter separation"
    if metric_type == "lineup":
        lineup_value = float(row["Lineup Boost"])
        if lineup_value >= 1.05:
            return "Impact bat quality stands out"
        if lineup_value >= 1.0:
            return "Offense should travel"
        return "Lineup support is still notable"
    if metric_type == "bullpen":
        bullpen_status = _get_bullpen_display_status(row["Bullpen Status"])
        if bullpen_status == "At Risk":
            return "Late innings look fragile"
        if bullpen_status == "Elevated":
            return "Relief load is building"
        return "Bullpen enters with some strain"
    return "Strongest overall profile on the board"


def _get_matchup_opponent(matchup_value, team_name):
    if matchup_value is None or pd.isna(matchup_value):
        return "board"
    matchup_text = str(matchup_value)
    if " at " not in matchup_text:
        return matchup_text
    away_team, home_team = matchup_text.split(" at ", 1)
    return home_team if str(team_name) == away_team else away_team


def _render_driver_tab_styles():
    st.markdown(
        """
        <style>
        .drivers-workspace-shell {
            display: grid;
            gap: 1.25rem;
        }
        .drivers-toolbar-shell {
            padding: 0.95rem 1rem;
            border-radius: 20px;
            border: 1px solid rgba(59, 130, 246, 0.16);
            background: linear-gradient(180deg, rgba(17, 24, 39, 0.94) 0%, rgba(15, 23, 42, 0.96) 100%);
            box-shadow: 0 14px 32px rgba(2, 6, 23, 0.28);
        }
        .driver-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 1rem;
        }
        .driver-grid > * {
            min-width: 0;
        }
        .driver-span-6 {
            grid-column: span 6;
        }
        .driver-span-12 {
            grid-column: span 12;
        }
        .driver-signal-card {
            padding: 1.1rem 1.15rem;
            border-radius: 22px;
            border: 1px solid rgba(96, 165, 250, 0.16);
            background:
                radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), transparent 34%),
                linear-gradient(180deg, rgba(18, 29, 45, 0.98) 0%, rgba(10, 22, 38, 0.98) 100%);
            box-shadow: 0 18px 40px rgba(2, 6, 23, 0.26);
            min-height: 176px;
        }
        .driver-card-eyebrow, .driver-panel-eyebrow {
            color: #7DD3FC;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.68rem;
            font-weight: 800;
        }
        .driver-card-headline {
            color: #F8FAFC;
            font-family: "Space Grotesk", "Barlow", sans-serif;
            font-size: 1.18rem;
            font-weight: 700;
            margin-top: 0.45rem;
        }
        .driver-card-team {
            color: #E2E8F0;
            font-size: 0.96rem;
            font-weight: 700;
            margin-top: 0.55rem;
        }
        .driver-card-metric {
            color: #F8FAFC;
            font-size: 1.55rem;
            font-weight: 800;
            margin-top: 0.5rem;
            line-height: 1.05;
        }
        .driver-card-note {
            color: #94A3B8;
            font-size: 0.84rem;
            line-height: 1.45;
            margin-top: 0.55rem;
        }
        .driver-section-shell {
            padding: 1.05rem 1.05rem 1.1rem;
            border-radius: 24px;
            border: 1px solid rgba(71, 85, 105, 0.38);
            background: linear-gradient(180deg, rgba(20, 27, 40, 0.96) 0%, rgba(12, 19, 31, 0.98) 100%);
            box-shadow: 0 16px 36px rgba(2, 6, 23, 0.22);
        }
        .driver-section-title {
            color: #F8FAFC;
            font-family: "Space Grotesk", "Barlow", sans-serif;
            font-size: 1.2rem;
            font-weight: 700;
        }
        .driver-section-heading {
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }
        .driver-section-icon {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 12px;
            background: rgba(59, 130, 246, 0.12);
            border: 1px solid rgba(96, 165, 250, 0.18);
            font-size: 1rem;
        }
        .driver-section-copy {
            color: #94A3B8;
            font-size: 0.86rem;
            margin-top: 0.24rem;
            margin-bottom: 0.95rem;
        }
        .pitcher-rank-grid, .identity-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 0.9rem;
        }
        .pitcher-rank-card, .identity-card, .split-board-card {
            border-radius: 20px;
            border: 1px solid rgba(71, 85, 105, 0.32);
            background: linear-gradient(180deg, rgba(24, 34, 50, 0.96) 0%, rgba(15, 23, 38, 0.98) 100%);
            padding: 0.95rem 1rem;
            min-height: 100%;
        }
        .pitcher-rank-card {
            grid-column: span 12;
        }
        .pitcher-rank-topline, .identity-topline, .split-board-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.65rem;
        }
        .pitcher-rank-chip, .identity-rank-chip {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 40px;
            height: 40px;
            border-radius: 14px;
            background: rgba(59, 130, 246, 0.14);
            border: 1px solid rgba(96, 165, 250, 0.24);
            color: #E0F2FE;
            font-size: 0.88rem;
            font-weight: 800;
        }
        .pitcher-rank-name, .identity-team {
            color: #F8FAFC;
            font-size: 1rem;
            font-weight: 700;
        }
        .pitcher-rank-meta, .identity-copy, .split-board-copy {
            color: #94A3B8;
            font-size: 0.82rem;
            margin-top: 0.2rem;
        }
        .pitcher-score-pill, .identity-profile-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.74rem;
            font-weight: 800;
            border: 1px solid rgba(148, 163, 184, 0.24);
            color: #E2E8F0;
            background: rgba(30, 41, 59, 0.7);
            white-space: nowrap;
        }
        .pitcher-rank-metrics, .identity-metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.85rem;
        }
        .identity-metrics {
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }
        .pitcher-rank-metric, .identity-metric {
            padding: 0.7rem 0.75rem;
            border-radius: 16px;
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.24);
        }
        .metric-label {
            color: #64748B;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        .metric-value {
            color: #F8FAFC;
            font-size: 0.94rem;
            font-weight: 700;
            margin-top: 0.2rem;
        }
        .driver-table-shell {
            border-radius: 18px;
            border: 1px solid rgba(71, 85, 105, 0.28);
            background: rgba(15, 23, 42, 0.62);
            overflow: hidden;
        }
        .driver-table {
            width: 100%;
            border-collapse: collapse;
        }
        .driver-table th {
            text-align: left;
            padding: 0.7rem 0.9rem;
            color: #94A3B8;
            font-size: 0.69rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            background: rgba(30, 41, 59, 0.86);
            border-bottom: 1px solid rgba(71, 85, 105, 0.24);
        }
        .driver-table td {
            padding: 0.82rem 0.9rem;
            color: #E2E8F0;
            border-bottom: 1px solid rgba(51, 65, 85, 0.45);
            font-size: 0.84rem;
        }
        .driver-table tbody tr:last-child td {
            border-bottom: none;
        }
        .driver-team-cell {
            font-weight: 700;
            color: #F8FAFC;
        }
        .driver-rank-cell {
            color: #7DD3FC;
            font-weight: 800;
        }
        .split-board-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 0.95rem;
        }
        .split-board-card {
            grid-column: span 6;
        }
        .split-board-title {
            color: #F8FAFC;
            font-size: 1rem;
            font-weight: 700;
        }
        .split-board-list {
            display: grid;
            gap: 0.65rem;
            margin-top: 0.85rem;
        }
        .split-board-row {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            gap: 0.7rem;
            align-items: center;
            padding: 0.72rem 0.78rem;
            border-radius: 16px;
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(71, 85, 105, 0.22);
        }
        .split-board-rank {
            color: #7DD3FC;
            font-size: 0.8rem;
            font-weight: 800;
        }
        .split-board-team {
            color: #F8FAFC;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .split-board-meta {
            color: #94A3B8;
            font-size: 0.76rem;
            margin-top: 0.16rem;
        }
        .driver-status-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.28rem 0.68rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            white-space: nowrap;
            border: 1px solid rgba(148, 163, 184, 0.20);
        }
        .status-fresh {
            color: #86EFAC;
            background: rgba(34, 197, 94, 0.14);
        }
        .status-stable {
            color: #BFDBFE;
            background: rgba(59, 130, 246, 0.14);
        }
        .status-taxed {
            color: #FCD34D;
            background: rgba(245, 158, 11, 0.16);
        }
        .status-risk {
            color: #FCA5A5;
            background: rgba(239, 68, 68, 0.16);
        }
        .identity-card {
            grid-column: span 6;
        }
        .compact-rank-list {
            display: grid;
            gap: 0.7rem;
        }
        .compact-rank-row {
            display: grid;
            grid-template-columns: auto minmax(0, 1.2fr) repeat(3, minmax(110px, 0.7fr));
            gap: 0.75rem;
            align-items: center;
            padding: 0.82rem 0.9rem;
            border-radius: 18px;
            border: 1px solid rgba(71, 85, 105, 0.24);
            background: linear-gradient(180deg, rgba(24, 34, 50, 0.92) 0%, rgba(15, 23, 38, 0.96) 100%);
        }
        .compact-rank-team {
            color: #F8FAFC;
            font-size: 0.94rem;
            font-weight: 700;
        }
        .compact-rank-meta {
            color: #94A3B8;
            font-size: 0.76rem;
            margin-top: 0.14rem;
        }
        .compact-rank-metric {
            text-align: left;
        }
        .compact-rank-label {
            color: #64748B;
            font-size: 0.67rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        .compact-rank-value {
            color: #F8FAFC;
            font-size: 0.88rem;
            font-weight: 700;
            margin-top: 0.18rem;
        }
        .identity-profile-pill.profile-offense {
            color: #86EFAC;
            background: rgba(34, 197, 94, 0.14);
        }
        .identity-profile-pill.profile-pitching {
            color: #93C5FD;
            background: rgba(59, 130, 246, 0.14);
        }
        .identity-profile-pill.profile-bullpen {
            color: #FCD34D;
            background: rgba(245, 158, 11, 0.16);
        }
        .identity-profile-pill.profile-balanced {
            color: #E2E8F0;
            background: rgba(148, 163, 184, 0.14);
        }
        .driver-subtle-note {
            color: #64748B;
            font-size: 0.74rem;
            margin-top: 0.7rem;
        }
        @media (min-width: 900px) {
            .pitcher-rank-card {
                grid-column: span 6;
            }
        }
        @media (min-width: 1200px) {
            .pitcher-rank-card {
                grid-column: span 4;
            }
        }
        @media (max-width: 980px) {
            .driver-span-6, .split-board-card, .identity-card {
                grid-column: span 12;
            }
            .pitcher-rank-metrics, .identity-metrics {
                grid-template-columns: 1fr;
            }
            .compact-rank-row {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_driver_insight_cards(cards):
    if not cards:
        return

    cards_html = ['<div class="driver-grid">']
    for card in cards:
        cards_html.append(
            dedent(
                f"""
                <div class="driver-signal-card driver-span-6">
                    <div class="driver-card-eyebrow">{escape(str(card["label"]))}</div>
                    <div class="driver-card-headline">{escape(str(card["headline"]))}</div>
                    <div class="driver-card-team">{escape(str(card["team"]))}</div>
                    <div class="driver-card-metric">{escape(str(card["metric"]))}</div>
                    <div class="driver-card-note">{escape(str(card["note"]))}</div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_pitcher_rank_cards(dataframe, max_rows=5):
    if dataframe is None or dataframe.empty:
        st.info("No starting pitcher signals are available yet.")
        return

    cards_html = ['<div class="pitcher-rank-grid">']
    for _, row in dataframe.head(max_rows).iterrows():
        cards_html.append(
            dedent(
                f"""
                <div class="pitcher-rank-card">
                    <div class="pitcher-rank-topline">
                        <div>
                            <div class="pitcher-rank-chip">#{int(row["Rank"])}</div>
                        </div>
                        <div style="flex:1;">
                            <div class="pitcher-rank-name">{escape(str(row["Pitcher"]))}</div>
                            <div class="pitcher-rank-meta">{escape(str(row["Team"]))} | {escape(str(row["Matchup"]))}</div>
                        </div>
                        <div class="pitcher-score-pill">{_get_pitcher_tier(row["Rank"])}</div>
                    </div>
                    <div class="pitcher-rank-metrics">
                        <div class="pitcher-rank-metric">
                            <div class="metric-label">Pitcher Score</div>
                            <div class="metric-value">{_format_driver_decimal(row["Pitcher Score"])}</div>
                        </div>
                        <div class="pitcher-rank-metric">
                            <div class="metric-label">FIP</div>
                            <div class="metric-value">{_format_driver_decimal(row["FIP"])}</div>
                        </div>
                        <div class="pitcher-rank-metric">
                            <div class="metric-label">Hand</div>
                            <div class="metric-value">{escape(_format_driver_hand(row["Throws"]))}</div>
                        </div>
                    </div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_driver_table(dataframe, columns, formatters=None, max_rows=5):
    if dataframe is None or dataframe.empty:
        st.info("No rows are available yet.")
        return

    table_df = dataframe.loc[:, [column for column in columns if column in dataframe.columns]].head(max_rows).copy()
    header_html = "".join(f"<th>{escape(column_name)}</th>" for column_name in table_df.columns)
    rows_html = []

    for _, row in table_df.iterrows():
        cell_html = []
        for column_name in table_df.columns:
            display_value = _format_monitor_table_value(column_name, row[column_name], formatters=formatters)
            cell_class = ""
            if column_name == "Rank":
                cell_class = ' class="driver-rank-cell"'
            elif column_name == "Team":
                cell_class = ' class="driver-team-cell"'
            cell_html.append(f"<td{cell_class}>{escape(str(display_value))}</td>")
        rows_html.append(f"<tr>{''.join(cell_html)}</tr>")

    st.markdown(
        dedent(
            f"""
            <div class="driver-table-shell">
                <table class="driver-table">
                    <thead>
                        <tr>{header_html}</tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _render_compact_rank_rows(dataframe, config, max_rows=8, meta_builder=None):
    if dataframe is None or dataframe.empty:
        st.info("No rows are available yet.")
        return

    rows_html = ['<div class="compact-rank-list">']
    for _, row in dataframe.head(max_rows).iterrows():
        metrics_html = []
        for item in config:
            value = item["formatter"](row.get(item["column"]))
            metrics_html.append(
                dedent(
                    f"""
                    <div class="compact-rank-metric">
                        <div class="compact-rank-label">{escape(item["label"])}</div>
                        <div class="compact-rank-value">{escape(value)}</div>
                    </div>
                    """
                ).strip()
            )
        meta_value = meta_builder(row) if meta_builder is not None else ""
        rows_html.append(
            dedent(
                f"""
                <div class="compact-rank-row">
                    <div class="split-board-rank">#{int(row["Rank"])}</div>
                    <div>
                        <div class="compact-rank-team">{escape(str(row["Team"]))}</div>
                        <div class="compact-rank-meta">{escape(meta_value)}</div>
                    </div>
                    {''.join(metrics_html)}
                </div>
                """
            ).strip()
        )
    rows_html.append("</div>")
    st.markdown("".join(rows_html), unsafe_allow_html=True)


def _render_bullpen_signal_board(leaders_df, stress_df, max_rows=5):
    cards_html = ['<div class="split-board-grid">']
    board_specs = [
        ("Best Bullpens", "Freshest quality arms with the least recent drag.", leaders_df, "leaders"),
        ("Most At-Risk Bullpens", "Relief groups carrying the most stress into today.", stress_df, "stress"),
    ]

    for title, subtitle, dataframe, board_type in board_specs:
        cards_html.append(
            dedent(
                f"""
                <div class="split-board-card">
                    <div class="split-board-head">
                        <div>
                            <div class="driver-panel-eyebrow">Bullpen Signals</div>
                            <div class="split-board-title">{escape(title)}</div>
                            <div class="split-board-copy">{escape(subtitle)}</div>
                        </div>
                    </div>
                    <div class="split-board-list">
                """
            ).strip()
        )

        if dataframe is None or dataframe.empty:
            cards_html.append('<div class="split-board-row"><div class="split-board-team">No bullpen data</div></div>')
        else:
            for _, row in dataframe.head(max_rows).iterrows():
                display_status = _get_bullpen_display_status(row.get("Bullpen Status"))
                status_class = {
                    "Fresh": "status-fresh",
                    "Stable": "status-stable",
                    "Taxed": "status-taxed",
                    "At Risk": "status-risk",
                }.get(display_status, "status-stable")
                if board_type == "leaders":
                    meta_text = (
                        f"Score {_format_driver_decimal(row.get('Bullpen Score'))} | "
                        f"IP last 3 {_format_driver_decimal(row.get('Relief IP Last 3'), digits=1)}"
                    )
                else:
                    meta_text = (
                        f"Fatigue {_format_driver_decimal(row.get('Fatigue Penalty'))} | "
                        f"Adj {_format_driver_decimal(row.get('Adjusted Bullpen'))}"
                    )
                cards_html.append(
                    dedent(
                        f"""
                        <div class="split-board-row">
                            <div class="split-board-rank">#{int(row["Rank"])}</div>
                            <div>
                                <div class="split-board-team">{escape(str(row["Team"]))}</div>
                                <div class="split-board-meta">{escape(meta_text)}</div>
                            </div>
                            <div class="driver-status-pill {status_class}">{escape(display_status)}</div>
                        </div>
                        """
                    ).strip()
                )

        cards_html.append("</div></div>")

    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_model_identity_cards(dataframe, max_rows=5):
    if dataframe is None or dataframe.empty:
        st.info("No model identity rows are available yet.")
        return

    cards_html = ['<div class="identity-grid">']
    for _, row in dataframe.head(max_rows).iterrows():
        profile_label = str(row["Model Driver"])
        cards_html.append(
            dedent(
                f"""
                <div class="identity-card">
                    <div class="identity-topline">
                        <div class="identity-rank-chip">#{int(row["Rank"])}</div>
                        <div style="flex:1;">
                            <div class="identity-team">{escape(str(row["Team"]))}</div>
                            <div class="identity-copy">Team identity board</div>
                        </div>
                        <div class="identity-profile-pill {_get_model_profile_tone(profile_label)}">{escape(profile_label)}</div>
                    </div>
                    <div class="identity-metrics">
                        <div class="identity-metric">
                            <div class="metric-label">Power</div>
                            <div class="metric-value">{_format_driver_decimal(row["Power Score"])}</div>
                        </div>
                        <div class="identity-metric">
                            <div class="metric-label">Offense</div>
                            <div class="metric-value">{_format_driver_decimal(row["Offense Score"])}</div>
                        </div>
                        <div class="identity-metric">
                            <div class="metric-label">Pitching</div>
                            <div class="metric-value">{_format_driver_decimal(row["Pitching Score"])}</div>
                        </div>
                        <div class="identity-metric">
                            <div class="metric-label">Volatility</div>
                            <div class="metric-value">{_format_driver_decimal(row["Volatility Score"])}</div>
                        </div>
                    </div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_top_leader_cards(dataframe, value_column, subtitle_builder, value_format, max_cards=5):
    if dataframe is None or dataframe.empty:
        return

    cards_html = ['<div class="leader-row">']
    top_slice = dataframe.head(max_cards)
    for _, row in top_slice.iterrows():
        cards_html.append(
            dedent(
                f"""
                <div class="leader-card">
                    <div class="leader-rank">#{int(row["Rank"])}</div>
                    <div class="leader-name">{row["Team"]}</div>
                    <div class="leader-value">{value_format(row[value_column])}</div>
                    <div class="leader-subtext">{subtitle_builder(row)}</div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _format_monitor_table_value(column_name, value, formatters=None):
    """Format leaderboard values for the custom dark table renderer."""
    if value is None or pd.isna(value):
        return "N/A"

    if formatters and column_name in formatters:
        return formatters[column_name](value)

    return str(value)


def _render_monitor_table_cell(column_name, value, formatters=None):
    """Render one monitor table cell, using badges for key status fields."""
    display_value = _format_monitor_table_value(column_name, value, formatters=formatters)

    badge_palette = {
        "Bullpen Status": {
            "Fresh": ("#2ECC71", "rgba(46, 204, 113, 0.16)", "rgba(46, 204, 113, 0.30)"),
            "Stable": ("#9BCB8F", "rgba(155, 203, 143, 0.15)", "rgba(155, 203, 143, 0.28)"),
            "Watch": ("#F1C40F", "rgba(241, 196, 15, 0.14)", "rgba(241, 196, 15, 0.28)"),
            "Stressed": ("#E67E22", "rgba(230, 126, 34, 0.14)", "rgba(230, 126, 34, 0.28)"),
        },
        "Lineup Confidence": {
            "Full": ("#2ECC71", "rgba(46, 204, 113, 0.16)", "rgba(46, 204, 113, 0.30)"),
            "Partial": ("#F1C40F", "rgba(241, 196, 15, 0.14)", "rgba(241, 196, 15, 0.28)"),
            "Thin": ("#E67E22", "rgba(230, 126, 34, 0.14)", "rgba(230, 126, 34, 0.28)"),
        },
        "Model Driver": {
            "Offense-Driven": ("#2ECC71", "rgba(46, 204, 113, 0.16)", "rgba(46, 204, 113, 0.30)"),
            "Pitching-Driven": ("#7FC7FF", "rgba(127, 199, 255, 0.16)", "rgba(127, 199, 255, 0.28)"),
            "Bullpen-Driven": ("#F39C12", "rgba(243, 156, 18, 0.16)", "rgba(243, 156, 18, 0.28)"),
            "Balanced": ("#C5CBD8", "rgba(139, 147, 167, 0.14)", "rgba(139, 147, 167, 0.26)"),
        },
    }

    if column_name in badge_palette and display_value in badge_palette[column_name]:
        color, background, border = badge_palette[column_name][display_value]
        return (
            f'<span style="display:inline-flex;align-items:center;justify-content:center;'
            f'padding:0.2rem 0.6rem;border-radius:999px;font-size:0.74rem;font-weight:700;'
            f'white-space:nowrap;color:{color};background:{background};border:1px solid {border};">'
            f"{display_value}</span>"
        )

    return display_value


def _render_monitor_leaderboard_table(dataframe, columns, formatters=None):
    """Render a dark, mobile-friendly leaderboard table for the Drivers tab."""
    if dataframe is None or dataframe.empty:
        st.info("No monitor rows are available yet.")
        return

    table_df = dataframe.loc[:, [column for column in columns if column in dataframe.columns]].copy()
    header_html = "".join(
        dedent(
            f"""
            <th class="monitor-table-head">{column_name}</th>
            """
        ).strip()
        for column_name in table_df.columns
    )

    rows_html = []
    for _, row in table_df.iterrows():
        cell_html = "".join(
            dedent(
                f"""
                <td class="monitor-table-cell">{_render_monitor_table_cell(column_name, row[column_name], formatters=formatters)}</td>
                """
            ).strip()
            for column_name in table_df.columns
        )
        rows_html.append(
            dedent(
                f"""
                <tr class="monitor-table-row">
                    {cell_html}
                </tr>
                """
            ).strip()
        )

    st.markdown(
        dedent(
            f"""
            <div class="monitor-table-shell">
                <table class="monitor-table">
                    <thead>
                        <tr>{header_html}</tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _render_top_five_leader_groups(leader_groups):
    if not leader_groups:
        return

    groups_html = ['<div class="leader-groups-grid">']
    for group in leader_groups:
        groups_html.append(
            dedent(
                f"""
                <div class="leader-group-card">
                    <div class="leader-group-title">{group["title"]}</div>
                    <div class="leader-group-copy">{group["subtitle"]}</div>
                    <div class="leader-group-list">
                """
            ).strip()
        )

        top_rows = group["dataframe"].head(5)
        for _, row in top_rows.iterrows():
            rank_value = int(row["Rank"])
            rank_class = f"rank-{rank_value}" if rank_value <= 3 else ""
            row_class = "top3" if rank_value <= 3 else ""
            groups_html.append(
                dedent(
                    f"""
                    <div class="leader-group-row {row_class}">
                        <div class="leader-group-rank {rank_class}">#{rank_value}</div>
                        <div class="leader-group-team">{row["Team"]}</div>
                        <div class="leader-group-metric">{group["value_format"](row[group["value_column"]])}</div>
                    </div>
                    """
                ).strip()
            )

        groups_html.append("</div></div>")

    groups_html.append("</div>")
    st.markdown("".join(groups_html), unsafe_allow_html=True)


def _filter_monitor_dataframe(dataframe, league_filter):
    if dataframe is None or dataframe.empty or league_filter == "MLB":
        return dataframe
    filtered_df = dataframe.copy()
    if "Division" in filtered_df.columns:
        return filtered_df.loc[filtered_df["Division"].str.startswith(league_filter)].reset_index(drop=True)
    if "Team" in filtered_df.columns:
        teams_in_league = {
            team_name
            for team_name, division_name in TEAM_TO_DIVISION.items()
            if division_name.startswith(league_filter)
        }
        return filtered_df.loc[filtered_df["Team"].isin(teams_in_league)].reset_index(drop=True)
    return filtered_df


def _get_monitor_row_limit(table_view):
    if table_view == "Top 10":
        return 10
    if table_view == "Top 25":
        return 25
    return None


def _slice_monitor_dataframe(dataframe, row_limit):
    if dataframe is None or dataframe.empty or row_limit is None:
        return dataframe
    return dataframe.head(row_limit).copy()


def build_pitcher_watch(pitcher_ratings_df, daily_board_inputs=None):
    if pitcher_ratings_df is None or pitcher_ratings_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    pitcher_df = pitcher_ratings_df.copy()
    required_columns = {
        "pitcher_name": "",
        "pitcher_rating": 1.00,
        "fip": np.nan,
        "throws": "",
    }
    for column_name, default_value in required_columns.items():
        if column_name not in pitcher_df.columns:
            pitcher_df[column_name] = default_value

    pitcher_df["pitcher_rating"] = pd.to_numeric(pitcher_df["pitcher_rating"], errors="coerce")
    pitcher_df["fip"] = pd.to_numeric(pitcher_df["fip"], errors="coerce")
    pitcher_df["throws"] = pitcher_df["throws"].fillna("").astype(str).str.upper()
    pitcher_df = pitcher_df.dropna(subset=["pitcher_name", "pitcher_rating"]).copy()
    pitcher_df = pitcher_df.rename(
        columns={
            "pitcher_name": "Pitcher",
            "pitcher_rating": "Pitcher Rating",
            "fip": "FIP",
            "throws": "Throws",
        }
    )
    pitcher_df["Pitcher Score"] = 1.0 / pitcher_df["Pitcher Rating"]
    pitcher_df = pitcher_df.sort_values(by=["Pitcher Rating", "FIP"], ascending=[True, True], na_position="last")
    pitcher_df = _add_rank_column(pitcher_df[["Pitcher", "Pitcher Score", "Pitcher Rating", "FIP", "Throws"]])

    today_df = pd.DataFrame(columns=["Pitcher", "Team", "Matchup", "Pitcher Score", "Pitcher Rating", "FIP", "Throws"])
    if daily_board_inputs is not None and not daily_board_inputs.empty:
        starter_rows = []
        seen_pitchers = set()
        for _, row in daily_board_inputs.iterrows():
            for team_column, pitcher_column in [("Away", "Away Pitcher"), ("Home", "Home Pitcher")]:
                pitcher_name = row.get(pitcher_column)
                if pitcher_name in {None, ""} or pd.isna(pitcher_name) or pitcher_name in seen_pitchers:
                    continue
                matching_row = pitcher_df.loc[pitcher_df["Pitcher"] == pitcher_name]
                if matching_row.empty:
                    continue
                seen_pitchers.add(pitcher_name)
                starter_rows.append(
                    {
                        "Pitcher": pitcher_name,
                        "Team": row.get(team_column),
                        "Matchup": f"{row.get('Away')} at {row.get('Home')}",
                        "Pitcher Score": float(matching_row.iloc[0]["Pitcher Score"]),
                        "Pitcher Rating": float(matching_row.iloc[0]["Pitcher Rating"]),
                        "FIP": matching_row.iloc[0]["FIP"],
                        "Throws": matching_row.iloc[0]["Throws"],
                    }
                )
        if starter_rows:
            today_df = pd.DataFrame(starter_rows).sort_values(
                by=["Pitcher Rating", "FIP"],
                ascending=[True, True],
                na_position="last",
            )
            today_df = _add_rank_column(today_df)

    return pitcher_df, today_df


def build_lineup_monitor(team_ratings_df, hitter_ratings_df, projected_lineups_df):
    if team_ratings_df is None or team_ratings_df.empty:
        return pd.DataFrame()

    team_rows = []
    for team_name in team_ratings_df.index.tolist():
        offense_score = float(
            (team_ratings_df.loc[team_name, "offense_vs_rhp"] + team_ratings_df.loc[team_name, "offense_vs_lhp"]) / 2.0
        )
        lineup_adjustment = calculate_lineup_adjustment(team_name, hitter_ratings_df, projected_lineups_df)
        projected_count = 0
        if projected_lineups_df is not None and not projected_lineups_df.empty and "team" in projected_lineups_df.columns:
            projected_count = int((projected_lineups_df["team"] == team_name).sum())
        lineup_power = offense_score * float(lineup_adjustment)
        team_rows.append(
            {
                "Team": team_name,
                "Lineup Score": round(lineup_power, 3),
                "Lineup Adjustment": round(float(lineup_adjustment), 3),
                "Offense Score": round(offense_score, 3),
                "Projected Hitters": projected_count,
                "Lineup Confidence": _get_lineup_confidence(projected_count),
            }
        )

    lineup_df = pd.DataFrame(team_rows).sort_values(
        by=["Lineup Score", "Lineup Adjustment", "Offense Score"],
        ascending=[False, False, False],
    )
    return _add_rank_column(lineup_df)


def build_bullpen_monitor(team_ratings_df):
    if team_ratings_df is None or team_ratings_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    usage_df = load_recent_bullpen_usage()
    bullpen_rows = []
    for team_name in team_ratings_df.index.tolist():
        bullpen_rating = float(team_ratings_df.loc[team_name, "bullpen"])
        fatigue = float(estimate_bullpen_fatigue(team_name, usage_df))
        adjusted_rating = bullpen_rating + fatigue
        relief_ip_last3 = 0.0
        if not usage_df.empty and "team" in usage_df.columns and "date" in usage_df.columns and "relief_ip" in usage_df.columns:
            team_usage = usage_df.loc[usage_df["team"] == team_name].copy()
            if not team_usage.empty:
                team_usage["date"] = pd.to_datetime(team_usage["date"], errors="coerce")
                team_usage["relief_ip"] = pd.to_numeric(team_usage["relief_ip"], errors="coerce")
                team_usage = team_usage.dropna(subset=["date", "relief_ip"])
                if not team_usage.empty:
                    latest_date = team_usage["date"].max()
                    cutoff_date = latest_date - pd.Timedelta(days=2)
                    relief_ip_last3 = float(team_usage.loc[team_usage["date"] >= cutoff_date, "relief_ip"].sum())
        bullpen_rows.append(
            {
                "Team": team_name,
                "Bullpen Score": round(1.0 / adjusted_rating, 3),
                "Bullpen Rating": round(bullpen_rating, 3),
                "Fatigue Penalty": round(fatigue, 3),
                "Relief IP Last 3": round(relief_ip_last3, 1),
                "Adjusted Bullpen": round(adjusted_rating, 3),
                "Bullpen Status": _get_bullpen_status(fatigue, relief_ip_last3),
            }
        )

    bullpen_df = pd.DataFrame(bullpen_rows)
    leaders_df = _add_rank_column(
        bullpen_df.sort_values(by=["Bullpen Score", "Fatigue Penalty"], ascending=[False, True]).copy()
    )
    stressed_df = _add_rank_column(
        bullpen_df.sort_values(by=["Fatigue Penalty", "Relief IP Last 3"], ascending=[False, False]).copy()
    )
    return leaders_df, stressed_df


def build_model_movers(team_ratings_df):
    if team_ratings_df is None or team_ratings_df.empty:
        return pd.DataFrame()

    movers_df = _build_talent_table(team_ratings_df)[
        ["Team", "Power Score", "Offense Score", "Pitching Score", "Bullpen Score"]
    ].copy()
    movers_df["Volatility Score"] = (
        movers_df[["Offense Score", "Pitching Score", "Bullpen Score"]].max(axis=1)
        - movers_df[["Offense Score", "Pitching Score", "Bullpen Score"]].min(axis=1)
    ).round(3)
    dominant_metric = movers_df[["Offense Score", "Pitching Score", "Bullpen Score"]].idxmax(axis=1)
    movers_df["Model Driver"] = np.where(
        movers_df["Volatility Score"] <= 0.03,
        "Balanced",
        np.where(
            dominant_metric == "Offense Score",
            "Offense Driven",
            np.where(dominant_metric == "Pitching Score", "Pitching Led", "Bullpen Led"),
        ),
    )
    movers_df = movers_df.sort_values(by=["Power Score", "Volatility Score"], ascending=[False, False])
    return _add_rank_column(
        movers_df[
            [
                "Team",
                "Model Driver",
                "Power Score",
                "Offense Score",
                "Pitching Score",
                "Bullpen Score",
                "Volatility Score",
            ]
        ]
    )


def build_today_impact(daily_board_inputs, bullpen_stress_df):
    if daily_board_inputs is None or daily_board_inputs.empty:
        return []

    impact_rows = []
    bullpen_lookup = {}
    if bullpen_stress_df is not None and not bullpen_stress_df.empty:
        bullpen_lookup = bullpen_stress_df.set_index("Team").to_dict("index")

    for _, row in daily_board_inputs.iterrows():
        away_team = row.get("Away")
        home_team = row.get("Home")
        away_sp = pd.to_numeric(row.get("Away SP"), errors="coerce")
        home_sp = pd.to_numeric(row.get("Home SP"), errors="coerce")
        away_lineup = pd.to_numeric(row.get("Away Lineup"), errors="coerce")
        home_lineup = pd.to_numeric(row.get("Home Lineup"), errors="coerce")

        starter_edge = None
        starter_team = None
        if pd.notna(away_sp) and pd.notna(home_sp) and away_sp > 0 and home_sp > 0:
            away_score = 1.0 / float(away_sp)
            home_score = 1.0 / float(home_sp)
            starter_edge = abs(away_score - home_score)
            starter_team = away_team if away_score >= home_score else home_team

        lineup_peak = None
        lineup_team = None
        if pd.notna(away_lineup) or pd.notna(home_lineup):
            away_lineup_value = float(away_lineup) if pd.notna(away_lineup) else float("-inf")
            home_lineup_value = float(home_lineup) if pd.notna(home_lineup) else float("-inf")
            lineup_peak = max(away_lineup_value, home_lineup_value)
            lineup_team = away_team if away_lineup_value >= home_lineup_value else home_team

        bullpen_risk_team = None
        bullpen_risk_value = None
        bullpen_status = None
        for team_name in [away_team, home_team]:
            bullpen_row = bullpen_lookup.get(team_name)
            if not bullpen_row:
                continue
            fatigue_value = float(bullpen_row.get("Fatigue Penalty", 0.0) or 0.0)
            if bullpen_risk_value is None or fatigue_value > bullpen_risk_value:
                bullpen_risk_value = fatigue_value
                bullpen_risk_team = team_name
                bullpen_status = bullpen_row.get("Bullpen Status")

        impact_rows.append(
            {
                "Matchup": f"{away_team} at {home_team}",
                "Starter Edge Team": starter_team,
                "Starter Edge": round(float(starter_edge), 3) if starter_edge is not None else None,
                "Lineup Boost Team": lineup_team,
                "Lineup Boost": round(float(lineup_peak), 3) if lineup_peak is not None else None,
                "Bullpen Risk Team": bullpen_risk_team,
                "Bullpen Risk": round(float(bullpen_risk_value), 3) if bullpen_risk_value is not None else None,
                "Bullpen Status": bullpen_status,
            }
        )

    if not impact_rows:
        return []

    impact_df = pd.DataFrame(impact_rows)
    cards = []

    starter_df = impact_df.dropna(subset=["Starter Edge"]).sort_values(by="Starter Edge", ascending=False)
    if not starter_df.empty:
        top_row = starter_df.iloc[0]
        opponent_name = _get_matchup_opponent(top_row["Matchup"], top_row["Starter Edge Team"])
        cards.append(
            {
                "label": "Starter Signal",
                "headline": "Strongest Starter Edge",
                "team": str(top_row["Starter Edge Team"]),
                "metric": f"{_format_driver_decimal(top_row['Starter Edge'], signed=True)} vs {opponent_name}",
                "note": _get_driver_note("starter", top_row),
            }
        )

    lineup_df = impact_df.dropna(subset=["Lineup Boost"]).sort_values(by="Lineup Boost", ascending=False)
    if not lineup_df.empty:
        top_row = lineup_df.iloc[0]
        cards.append(
            {
                "label": "Lineup Signal",
                "headline": "Biggest Lineup Edge",
                "team": str(top_row["Lineup Boost Team"]),
                "metric": f"Adj {_format_driver_decimal(top_row['Lineup Boost'])}",
                "note": _get_driver_note("lineup", top_row),
            }
        )

    bullpen_df = impact_df.dropna(subset=["Bullpen Risk"]).sort_values(by="Bullpen Risk", ascending=False)
    if not bullpen_df.empty:
        top_row = bullpen_df.iloc[0]
        cards.append(
            {
                "label": "Bullpen Signal",
                "headline": "Highest Bullpen Risk",
                "team": str(top_row["Bullpen Risk Team"]),
                "metric": _get_bullpen_display_status(top_row["Bullpen Status"]),
                "note": _get_driver_note("bullpen", top_row),
            }
        )

    return cards


def _get_lineup_confidence(projected_count):
    if projected_count >= 9:
        return "Full"
    if projected_count >= 6:
        return "Partial"
    return "Thin"


def _get_bullpen_status(fatigue_penalty, relief_ip_last3):
    if fatigue_penalty >= 0.08 or relief_ip_last3 >= 14:
        return "Stressed"
    if fatigue_penalty >= 0.05 or relief_ip_last3 >= 10:
        return "Watch"
    if fatigue_penalty > 0.0 or relief_ip_last3 >= 6:
        return "Stable"
    return "Fresh"


def _render_monitor_summary_cards(cards):
    cards_html = ['<div class="monitor-summary-grid">']
    for card in cards:
        cards_html.append(
            dedent(
                f"""
                <div class="monitor-summary-card">
                    <div class="monitor-summary-label">{card["label"]}</div>
                    <div class="monitor-summary-team">{card["team"]}</div>
                    <div class="monitor-summary-value">{card["value"]}</div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_monitor_notes(notes):
    notes_html = ['<div class="monitor-notes">']
    for note in notes:
        notes_html.append(
            dedent(
                f"""
                <div class="monitor-note-card">
                    <div class="monitor-note-label">{note["label"]}</div>
                    <div class="monitor-note-value">{note["value"]}</div>
                </div>
                """
            ).strip()
        )
    notes_html.append("</div>")
    st.markdown("".join(notes_html), unsafe_allow_html=True)


def _format_team_profile_value(dataframe, column_name, formatter):
    if dataframe is None or dataframe.empty or column_name not in dataframe.columns:
        return "N/A"
    return formatter(dataframe.iloc[0][column_name])


def _render_team_profile_card(
    team_name,
    projected_df,
    offense_df,
    pitching_df,
    bullpen_df,
    power_df,
):
    if not team_name:
        return

    projected_wins = _format_team_profile_value(projected_df, "Projected Wins", lambda value: f"{float(value):.1f}")
    projected_win_pct = _format_team_profile_value(projected_df, "Projected Win %", lambda value: f"{float(value):.3f}")
    offense_score = _format_team_profile_value(offense_df, "Offense Score", lambda value: f"{float(value):.3f}")
    staff_score = _format_team_profile_value(pitching_df, "Staff Score", lambda value: f"{float(value):.3f}")
    bullpen_score = _format_team_profile_value(bullpen_df, "Bullpen Score", lambda value: f"{float(value):.3f}")
    power_score = _format_team_profile_value(power_df, "Power Score", lambda value: f"{float(value):.3f}")
    projected_rank = _format_team_profile_value(projected_df, "Rank", lambda value: f"#{int(value)}")
    power_rank = _format_team_profile_value(power_df, "Rank", lambda value: f"#{int(value)}")

    st.markdown(
        dedent(
            f"""
            <div class="team-profile-card">
                <div class="team-profile-kicker">Team profile</div>
                <div class="team-profile-title">{team_name}</div>
                <div class="team-profile-copy">
                    Single-team monitor mode highlights how this club grades out in the season model across projected wins,
                    overall power, offense, staff quality, and bullpen strength.
                </div>
                <div class="team-profile-grid">
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Projected Wins</div>
                        <div class="team-profile-value">{projected_wins}</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Projected Win %</div>
                        <div class="team-profile-value">{projected_win_pct}</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Projected Rank</div>
                        <div class="team-profile-value">{projected_rank}</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Power Score</div>
                        <div class="team-profile-value">{power_score} ({power_rank})</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Offense Score</div>
                        <div class="team-profile-value">{offense_score}</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Staff Score</div>
                        <div class="team-profile-value">{staff_score}</div>
                    </div>
                    <div class="team-profile-metric">
                        <div class="team-profile-label">Bullpen Score</div>
                        <div class="team-profile-value">{bullpen_score}</div>
                    </div>
                </div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _get_best_pitcher_driver_card(today_pitchers_view, pitcher_watch_view):
    if today_pitchers_view is not None and not today_pitchers_view.empty:
        top_row = today_pitchers_view.iloc[0]
        return {
            "team": top_row["Pitcher"],
            "value": f"Today | {top_row.get('Team', 'N/A')}",
        }
    if pitcher_watch_view is not None and not pitcher_watch_view.empty:
        top_row = pitcher_watch_view.iloc[0]
        return {
            "team": top_row["Pitcher"],
            "value": f"Pitcher score {float(top_row['Pitcher Score']):.3f}",
        }
    return {
        "team": "No pitcher data",
        "value": "Pitcher ratings unavailable",
    }


def _render_standings_race_cards(league_name, division_leader_slice, wildcard_slice, bubble_slice):
    cards_html = ['<div class="leader-groups-grid">']
    card_specs = [
        ("Division Leaders", division_leader_slice, lambda row: row["Division"], lambda row: f"{float(row['Projected Wins']):.1f} wins"),
        ("Wild Card Line", wildcard_slice, lambda row: f"WC{int(row['Wildcard Rank'])}", lambda row: f"{float(row['Playoff Odds']):.1f}% playoff"),
        ("Bubble Watch", bubble_slice, lambda row: "Chasing", lambda row: f"{float(row['Games Behind Cutline']):.1f} back"),
    ]

    for title, dataframe, sublabel_builder, metric_builder in card_specs:
        cards_html.append(
            dedent(
                f"""
                <div class="leader-group-card">
                    <div class="leader-group-title">{league_name} {title}</div>
                    <div class="leader-group-copy">Fast-read playoff race snapshot.</div>
                    <div class="leader-group-list">
                """
            ).strip()
        )

        if dataframe.empty:
            cards_html.append(
                '<div class="leader-group-row"><div class="leader-group-rank">-</div><div class="leader-group-team">No teams</div><div class="leader-group-metric">N/A</div></div>'
            )
        else:
            for _, row in dataframe.iterrows():
                rank_text = (
                    row["Division"].replace("AL ", "").replace("NL ", "")
                    if "Division" in row
                    else f"#{int(row['Wildcard Rank'])}"
                )
                cards_html.append(
                    dedent(
                        f"""
                        <div class="leader-group-row top3">
                            <div class="leader-group-rank rank-1">{rank_text}</div>
                            <div class="leader-group-team">{row["Team"]}</div>
                            <div class="leader-group-metric">{metric_builder(row)}</div>
                        </div>
                        """
                    ).strip()
                )

        cards_html.append("</div></div>")

    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _style_playoff_outlook(value):
    tone_map = {
        "Division Leader": "background-color: rgba(46, 204, 113, 0.18); color: #2ECC71; font-weight: 700;",
        "Wild Card": "background-color: rgba(243, 156, 18, 0.18); color: #F39C12; font-weight: 700;",
        "Bubble": "background-color: rgba(241, 196, 15, 0.16); color: #F1C40F; font-weight: 700;",
        "Outside": "background-color: rgba(139, 147, 167, 0.14); color: #B5BAC7;",
    }
    return tone_map.get(value, "")


def _style_cutline_trend(value):
    tone_map = {
        "IN": "background-color: rgba(46, 204, 113, 0.18); color: #2ECC71; font-weight: 700;",
        "WATCH": "background-color: rgba(241, 196, 15, 0.16); color: #F1C40F; font-weight: 700;",
        "BACK": "background-color: rgba(139, 147, 167, 0.14); color: #B5BAC7;",
    }
    return tone_map.get(value, "")


def _style_odds_value(value):
    if pd.isna(value):
        return ""
    if float(value) >= 80.0:
        return "color: #2ECC71; font-weight: 700;"
    if float(value) >= 40.0:
        return "color: #F1C40F; font-weight: 700;"
    return "color: #B5BAC7;"


def _style_bullpen_status(value):
    tone_map = {
        "Fresh": "background-color: rgba(46, 204, 113, 0.18); color: #2ECC71; font-weight: 700;",
        "Stable": "background-color: rgba(139, 147, 167, 0.14); color: #B5BAC7; font-weight: 700;",
        "Watch": "background-color: rgba(241, 196, 15, 0.16); color: #F1C40F; font-weight: 700;",
        "Stressed": "background-color: rgba(231, 76, 60, 0.16); color: #E74C3C; font-weight: 700;",
    }
    return tone_map.get(value, "")


def _style_lineup_confidence(value):
    tone_map = {
        "Full": "background-color: rgba(46, 204, 113, 0.18); color: #2ECC71; font-weight: 700;",
        "Partial": "background-color: rgba(241, 196, 15, 0.16); color: #F1C40F; font-weight: 700;",
        "Thin": "background-color: rgba(231, 76, 60, 0.16); color: #E74C3C; font-weight: 700;",
    }
    return tone_map.get(value, "")


def _style_standings_table(dataframe):
    styled = dataframe.style
    if "Playoff Outlook" in dataframe.columns:
        styled = styled.map(_style_playoff_outlook, subset=["Playoff Outlook"])
    if "Cutline Trend" in dataframe.columns:
        styled = styled.map(_style_cutline_trend, subset=["Cutline Trend"])
    for column_name in ["Division Odds", "Wildcard Odds", "Playoff Odds"]:
        if column_name in dataframe.columns:
            styled = styled.map(_style_odds_value, subset=[column_name])
    return styled


def _style_monitor_table(dataframe):
    styled = dataframe.style
    if "Bullpen Status" in dataframe.columns:
        styled = styled.map(_style_bullpen_status, subset=["Bullpen Status"])
    if "Lineup Confidence" in dataframe.columns:
        styled = styled.map(_style_lineup_confidence, subset=["Lineup Confidence"])
    return styled


def _filter_standings_view(standings_df, wildcard_df, filter_value):
    if filter_value == "All":
        return standings_df.copy(), wildcard_df.copy()
    if filter_value in {"AL", "NL"}:
        return (
            standings_df.loc[standings_df["League"] == filter_value].copy(),
            wildcard_df.loc[wildcard_df["League"] == filter_value].copy(),
        )
    return (
        standings_df.loc[standings_df["Division"] == filter_value].copy(),
        wildcard_df.loc[wildcard_df["Division"] == filter_value].copy(),
    )


def _render_standings_filter_bar():
    st.markdown(
        """
        <div class="monitor-toolbar-shell">
            <div class="monitor-toolbar-topline">
                <div>
                    <div class="monitor-toolbar-kicker">Projection controls</div>
                    <div class="monitor-toolbar-title">Season scope</div>
                </div>
            </div>
        """,
        unsafe_allow_html=True,
    )
    scope_col, division_col = st.columns([1.0, 1.6])
    with scope_col:
        st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">League</div>', unsafe_allow_html=True)
        league_scope = st.radio(
            "Standings League",
            ["All", "AL", "NL"],
            key="standings_league_scope",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with division_col:
        division_options = ["All"]
        if league_scope in {"AL", "NL"}:
            division_options.extend([division for division in DIVISION_ORDER if division.startswith(league_scope)])
        st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">Division</div>', unsafe_allow_html=True)
        division_scope = st.radio(
            "Standings Division",
            division_options,
            key="standings_division_scope",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if league_scope == "All" or division_scope == "All":
        return league_scope
    return division_scope


def _render_projection_workspace_styles():
    st.markdown(
        """
        <style>
        .projection-shell {
            display: grid;
            gap: 1rem;
        }
        .projection-hero,
        .projection-surface,
        .about-hero,
        .about-surface {
            border-radius: 26px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.98) 100%);
            border: 1px solid rgba(226, 232, 240, 0.92);
            box-shadow: 0 18px 42px rgba(15, 23, 42, 0.16);
            color: #0F172A;
        }
        .projection-hero,
        .about-hero {
            padding: 1.35rem 1.45rem;
        }
        .projection-surface,
        .about-surface {
            padding: 1.1rem 1.15rem 1.15rem;
        }
        .projection-kicker,
        .about-kicker {
            color: #C2410C;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.68rem;
            font-weight: 800;
        }
        .projection-title,
        .about-title {
            color: #0F172A;
            font-family: "Space Grotesk", "Barlow", sans-serif;
            font-size: 2rem;
            font-weight: 700;
            margin-top: 0.42rem;
            line-height: 1.05;
        }
        .projection-copy,
        .about-copy {
            color: #475569;
            font-size: 0.94rem;
            line-height: 1.55;
            margin-top: 0.5rem;
            max-width: 860px;
        }
        .projection-section-title,
        .about-section-title {
            color: #0F172A;
            font-family: "Space Grotesk", "Barlow", sans-serif;
            font-size: 1.12rem;
            font-weight: 700;
        }
        .projection-section-copy,
        .about-section-copy {
            color: #64748B;
            font-size: 0.84rem;
            margin-top: 0.2rem;
            margin-bottom: 0.9rem;
        }
        .projection-outlook-grid,
        .about-grid,
        .coming-soon-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 0.9rem;
        }
        .projection-outlook-card,
        .about-card,
        .coming-soon-card,
        .projection-tier-card {
            grid-column: span 3;
            min-width: 0;
            border-radius: 22px;
            border: 1px solid rgba(226, 232, 240, 0.96);
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
            padding: 1rem 1rem 1.05rem;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        }
        .projection-outlook-label,
        .about-card-label,
        .coming-soon-label {
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.68rem;
            font-weight: 800;
        }
        .projection-outlook-value,
        .about-card-title,
        .coming-soon-title {
            color: #0F172A;
            font-size: 1.08rem;
            font-weight: 700;
            margin-top: 0.45rem;
            line-height: 1.25;
        }
        .projection-outlook-metric {
            color: #0F172A;
            font-size: 1.55rem;
            font-weight: 800;
            margin-top: 0.52rem;
            line-height: 1.05;
        }
        .projection-outlook-helper,
        .about-card-copy,
        .coming-soon-copy {
            color: #64748B;
            font-size: 0.82rem;
            line-height: 1.5;
            margin-top: 0.52rem;
        }
        .projection-tier-grid {
            display: grid;
            grid-template-columns: repeat(12, minmax(0, 1fr));
            gap: 0.9rem;
        }
        .projection-tier-title {
            color: #0F172A;
            font-size: 1rem;
            font-weight: 700;
        }
        .projection-tier-copy {
            color: #64748B;
            font-size: 0.8rem;
            margin-top: 0.2rem;
        }
        .projection-chip-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }
        .projection-chip {
            display: inline-flex;
            flex-direction: column;
            gap: 0.16rem;
            border-radius: 16px;
            padding: 0.7rem 0.8rem;
            min-width: 124px;
            background: linear-gradient(180deg, #F8FAFC 0%, #EFF6FF 100%);
            border: 1px solid rgba(191, 219, 254, 0.86);
        }
        .projection-chip-team {
            color: #0F172A;
            font-size: 0.84rem;
            font-weight: 700;
        }
        .projection-chip-meta {
            color: #64748B;
            font-size: 0.72rem;
        }
        .projection-table-shell {
            overflow: hidden;
            border-radius: 22px;
            border: 1px solid rgba(226, 232, 240, 0.96);
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
        }
        .projection-table {
            width: 100%;
            border-collapse: collapse;
        }
        .projection-table thead th {
            text-align: left;
            padding: 0.82rem 0.9rem;
            color: #64748B;
            font-size: 0.69rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            background: rgba(248, 250, 252, 0.98);
            border-bottom: 1px solid rgba(226, 232, 240, 0.9);
        }
        .projection-table tbody tr:nth-child(odd) {
            background: rgba(248, 250, 252, 0.78);
        }
        .projection-table tbody tr:nth-child(even) {
            background: rgba(255, 255, 255, 0.98);
        }
        .projection-table tbody tr:hover {
            background: rgba(239, 246, 255, 0.92);
        }
        .projection-table td {
            padding: 0.95rem 0.9rem;
            border-bottom: 1px solid rgba(226, 232, 240, 0.72);
            vertical-align: middle;
            color: #334155;
            font-size: 0.84rem;
        }
        .projection-table tbody tr:last-child td {
            border-bottom: none;
        }
        .projection-rank {
            color: #94A3B8;
            font-weight: 700;
            width: 36px;
        }
        .projection-team-name {
            color: #0F172A;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.15;
        }
        .projection-team-meta {
            color: #64748B;
            font-size: 0.74rem;
            margin-top: 0.18rem;
        }
        .projection-key-stat {
            color: #0F172A;
            font-size: 1.1rem;
            font-weight: 800;
            line-height: 1.1;
        }
        .projection-sub-stat {
            color: #64748B;
            font-size: 0.72rem;
            margin-top: 0.18rem;
        }
        .projection-pill {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            padding: 0.28rem 0.68rem;
            font-size: 0.72rem;
            font-weight: 800;
            border: 1px solid rgba(226, 232, 240, 0.96);
            background: #FFFFFF;
            color: #334155;
            white-space: nowrap;
        }
        .projection-pill.positive {
            color: #166534;
            background: rgba(220, 252, 231, 0.9);
            border-color: rgba(187, 247, 208, 0.95);
        }
        .projection-pill.warning {
            color: #9A3412;
            background: rgba(255, 237, 213, 0.95);
            border-color: rgba(254, 215, 170, 0.95);
        }
        .projection-pill.neutral {
            color: #475569;
            background: rgba(241, 245, 249, 0.95);
            border-color: rgba(226, 232, 240, 0.95);
        }
        .leader-groups-grid {
            margin: 0.15rem 0 0;
        }
        .leader-group-card {
            border-radius: 22px;
            padding: 1rem 1.02rem;
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
            border: 1px solid rgba(226, 232, 240, 0.96);
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        }
        .leader-group-title {
            color: #0F172A;
        }
        .leader-group-copy {
            color: #64748B;
        }
        .leader-group-row {
            background: rgba(248, 250, 252, 0.9);
            border: 1px solid rgba(226, 232, 240, 0.9);
        }
        .leader-group-row.top3 {
            border-color: rgba(254, 215, 170, 0.95);
            box-shadow: inset 0 0 0 1px rgba(251, 146, 60, 0.08);
        }
        .leader-group-team {
            color: #0F172A;
        }
        .leader-group-metric {
            color: #166534;
        }
        .about-grid .about-card {
            grid-column: span 4;
        }
        .about-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 34px;
            height: 34px;
            border-radius: 12px;
            background: linear-gradient(180deg, #FFF7ED 0%, #FFEDD5 100%);
            border: 1px solid rgba(254, 215, 170, 0.95);
            color: #C2410C;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.06em;
        }
        .about-card-topline {
            display: flex;
            align-items: center;
            gap: 0.7rem;
        }
        .about-card-blocks {
            display: grid;
            gap: 0.75rem;
            margin-top: 0.9rem;
        }
        .about-mini-block {
            border-radius: 16px;
            border: 1px solid rgba(226, 232, 240, 0.95);
            background: rgba(248, 250, 252, 0.88);
            padding: 0.82rem 0.86rem;
        }
        .about-mini-title {
            color: #0F172A;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .about-mini-copy {
            color: #64748B;
            font-size: 0.74rem;
            line-height: 1.45;
            margin-top: 0.22rem;
        }
        .coming-soon-card {
            grid-column: span 4;
        }
        @media (max-width: 1180px) {
            .projection-outlook-card,
            .projection-tier-card,
            .about-grid .about-card,
            .coming-soon-card {
                grid-column: span 6;
            }
        }
        @media (max-width: 760px) {
            .projection-outlook-card,
            .projection-tier-card,
            .about-grid .about-card,
            .coming-soon-card {
                grid-column: span 12;
            }
            .projection-title,
            .about-title {
                font-size: 1.6rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_projection_pct(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1f}%"


def _format_projection_wins(value):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1f}"


def _get_projection_pill_tone(playoff_outlook):
    if playoff_outlook == "Division Leader":
        return "positive"
    if playoff_outlook in {"Wild Card", "Bubble"}:
        return "warning"
    return "neutral"


def _build_projection_summary_cards(standings_df):
    if standings_df is None or standings_df.empty:
        return []

    ordered_df = standings_df.sort_values(
        by=["Projected Wins", "Power Score", "Playoff Odds"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    best_team = ordered_df.iloc[0]
    highest_wins = ordered_df.iloc[0]

    division_gap_df = (
        ordered_df.sort_values(by=["Division", "Projected Wins"], ascending=[True, False])
        .groupby("Division")
        .head(2)
        .copy()
    )
    tightest_race = None
    race_gap = None
    if not division_gap_df.empty:
        for division_name, division_slice in division_gap_df.groupby("Division"):
            if len(division_slice) < 2:
                continue
            division_slice = division_slice.sort_values(by="Projected Wins", ascending=False).reset_index(drop=True)
            gap_value = float(division_slice.loc[0, "Projected Wins"] - division_slice.loc[1, "Projected Wins"])
            if race_gap is None or gap_value < race_gap:
                race_gap = gap_value
                tightest_race = {
                    "division": division_name,
                    "leader": division_slice.loc[0, "Team"],
                    "challenger": division_slice.loc[1, "Team"],
                    "gap": gap_value,
                }

    power_rank_df = ordered_df.sort_values(by=["Power Score"], ascending=False).reset_index(drop=True)
    power_rank_df["Power Rank"] = power_rank_df.index + 1
    sleeper_candidates = power_rank_df.loc[
        (power_rank_df["Power Rank"] >= 9) | (power_rank_df["Projected Wins"] < 86.0)
    ].copy()
    if sleeper_candidates.empty:
        sleeper_row = ordered_df.iloc[min(len(ordered_df) - 1, 3)]
    else:
        sleeper_candidates["Sleeper Score"] = (
            sleeper_candidates["Playoff Odds"].fillna(0.0)
            + (100.0 - sleeper_candidates["Power Rank"] * 5.0)
        )
        sleeper_row = sleeper_candidates.sort_values(
            by=["Sleeper Score", "Playoff Odds", "Projected Wins"],
            ascending=[False, False, False],
        ).iloc[0]

    cards = [
        {
            "label": "Best Team",
            "title": str(best_team["Team"]),
            "metric": f"{float(best_team['Playoff Odds']):.1f}% playoff",
            "helper": f"Power leader with {float(best_team['Projected Wins']):.1f} projected wins.",
        },
        {
            "label": "Highest Projected Wins",
            "title": str(highest_wins["Team"]),
            "metric": f"{float(highest_wins['Projected Wins']):.1f} wins",
            "helper": f"Best full-season outlook in the current projection set.",
        },
        {
            "label": "Tightest Division Race",
            "title": tightest_race["division"] if tightest_race else "No race data",
            "metric": f"{tightest_race['gap']:.1f} game gap" if tightest_race else "N/A",
            "helper": (
                f"{tightest_race['leader']} vs {tightest_race['challenger']}."
                if tightest_race
                else "Need at least two teams in a division to compare."
            ),
        },
        {
            "label": "Biggest Surprise",
            "title": str(sleeper_row["Team"]),
            "metric": f"{float(sleeper_row['Playoff Odds']):.1f}% playoff",
            "helper": f"Sleeper case built on {float(sleeper_row['Projected Wins']):.1f} projected wins and a lower preseason profile.",
        },
    ]
    return cards


def _render_projection_summary_cards(cards):
    if not cards:
        return

    card_html = ['<div class="projection-outlook-grid">']
    for card in cards:
        card_html.append(
            dedent(
                f"""
                <div class="projection-outlook-card">
                    <div class="projection-outlook-label">{escape(str(card["label"]))}</div>
                    <div class="projection-outlook-value">{escape(str(card["title"]))}</div>
                    <div class="projection-outlook-metric">{escape(str(card["metric"]))}</div>
                    <div class="projection-outlook-helper">{escape(str(card["helper"]))}</div>
                </div>
                """
            ).strip()
        )
    card_html.append("</div>")
    st.markdown("".join(card_html), unsafe_allow_html=True)


def _build_team_tiers(standings_df):
    if standings_df is None or standings_df.empty:
        return []

    tier_specs = [
        ("Elite", "True upper-tier clubs with championship-level playoff odds.", standings_df["Playoff Odds"] >= 85.0),
        ("Playoff", "Clear postseason paths with fewer obvious questions.", (standings_df["Playoff Odds"] >= 55.0) & (standings_df["Playoff Odds"] < 85.0)),
        ("Fringe", "Live teams hovering around the cutline.", (standings_df["Playoff Odds"] >= 20.0) & (standings_df["Playoff Odds"] < 55.0)),
        ("Rebuilding", "Longer-shot profiles still playing more for future shape.", standings_df["Playoff Odds"] < 20.0),
    ]

    tiers = []
    for title, copy_text, mask in tier_specs:
        tier_df = standings_df.loc[mask].sort_values(
            by=["Projected Wins", "Playoff Odds", "Power Score"],
            ascending=[False, False, False],
        )
        tiers.append(
            {
                "title": title,
                "copy": copy_text,
                "teams": tier_df.head(8),
            }
        )
    return tiers


def _render_team_tiers(tiers):
    if not tiers:
        return

    tiers_html = ['<div class="projection-tier-grid">']
    for tier in tiers:
        chips_html = []
        teams_df = tier["teams"]
        if teams_df is not None and not teams_df.empty:
            for _, row in teams_df.iterrows():
                chips_html.append(
                    dedent(
                        f"""
                        <div class="projection-chip">
                            <div class="projection-chip-team">{escape(str(row["Team"]))}</div>
                            <div class="projection-chip-meta">{escape(f"{float(row['Projected Wins']):.1f} wins | {float(row['Playoff Odds']):.1f}% playoff")}</div>
                        </div>
                        """
                    ).strip()
                )
        else:
            chips_html.append(
                '<div class="projection-chip"><div class="projection-chip-team">Waiting on a stronger signal</div><div class="projection-chip-meta">No teams currently fit this tier.</div></div>'
            )

        tiers_html.append(
            dedent(
                f"""
                <div class="projection-tier-card">
                    <div class="projection-tier-title">{escape(str(tier["title"]))}</div>
                    <div class="projection-tier-copy">{escape(str(tier["copy"]))}</div>
                    <div class="projection-chip-list">
                        {''.join(chips_html)}
                    </div>
                </div>
                """
            ).strip()
        )
    tiers_html.append("</div>")
    st.markdown("".join(tiers_html), unsafe_allow_html=True)


def _render_projection_table(standings_df):
    if standings_df is None or standings_df.empty:
        st.markdown(
            """
            <div class="projection-surface">
                <div class="projection-section-title">Projected Standings</div>
                <div class="projection-section-copy">Season table will populate once team ratings and schedule data are available.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    display_df = standings_df.sort_values(
        by=["Projected Wins", "Playoff Odds", "Power Score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    rows_html = []
    for idx, row in display_df.iterrows():
        rows_html.append(
            dedent(
                f"""
                <tr>
                    <td class="projection-rank">{idx + 1}</td>
                    <td>
                        <div class="projection-team-name">{escape(str(row["Team"]))}</div>
                        <div class="projection-team-meta">{escape(str(row["Division"]))} | {escape(str(row["Playoff Outlook"]))}</div>
                    </td>
                    <td>{escape(f"{int(row['Actual Wins'])}-{int(row['Actual Losses'])}")}</td>
                    <td>
                        <div class="projection-key-stat">{escape(f"{float(row['Projected Wins']):.1f}")}</div>
                        <div class="projection-sub-stat">{escape(f"{float(row['Projected Win %']):.3f} projected win pct")}</div>
                    </td>
                    <td>
                        <div class="projection-key-stat">{escape(f"{float(row['Playoff Odds']):.1f}%")}</div>
                        <div class="projection-sub-stat">{escape(f"{float(row['Division Odds']):.1f}% division")}</div>
                    </td>
                    <td>
                        <span class="projection-pill {_get_projection_pill_tone(row['Playoff Outlook'])}">{escape(str(row["Playoff Outlook"]))}</span>
                    </td>
                </tr>
                """
            ).strip()
        )

    st.markdown(
        dedent(
            f"""
            <div class="projection-table-shell">
                <table class="projection-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Team</th>
                            <th>Actual</th>
                            <th>Proj Wins</th>
                            <th>Playoff</th>
                            <th>Outlook</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows_html)}
                    </tbody>
                </table>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _render_projection_coming_soon():
    cards = [
        {
            "label": "Coming Soon",
            "title": "Playoff probability chart",
            "copy": "A visual curve for each contender so you can compare true separation instead of scanning percentages row by row.",
        },
        {
            "label": "Coming Soon",
            "title": "Division race tracker",
            "copy": "A tighter race monitor that highlights leader changes, shrinking gaps, and who controls the most leverage games left.",
        },
        {
            "label": "Coming Soon",
            "title": "Season win distribution",
            "copy": "Projected win ranges and distribution bands for each club, designed for a faster read on volatility and ceiling outcomes.",
        },
    ]

    cards_html = ['<div class="coming-soon-grid">']
    for card in cards:
        cards_html.append(
            dedent(
                f"""
                <div class="coming-soon-card">
                    <div class="coming-soon-label">{escape(str(card["label"]))}</div>
                    <div class="coming-soon-title">{escape(str(card["title"]))}</div>
                    <div class="coming-soon-copy">{escape(str(card["copy"]))}</div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def _render_about_cards():
    blocks = [
        {
            "badge": "MW",
            "title": "How the model works",
            "copy": "The board starts with team and pitcher strength, simulates game outcomes, and turns those results into win probabilities before any sportsbook comparison is made.",
            "items": [
                ("Probability first", "Model win probability is the core output."),
                ("Market compare", "Odds are converted into implied and no-vig probabilities."),
                ("Signals", "Edge and EV help separate passes, leans, and stronger looks."),
            ],
        },
        {
            "badge": "DS",
            "title": "Data sources",
            "copy": "The app combines stored game results, lineup inputs, pitcher ratings, bullpen usage, and market odds into one betting workspace.",
            "items": [
                ("Results and schedule", "Historical MLB games stored in SQLite."),
                ("Ratings inputs", "Team, pitcher, and hitter CSV model inputs."),
                ("Market data", "Sportsbook odds snapshots used for implied probability."),
            ],
        },
        {
            "badge": "RF",
            "title": "Refresh timing",
            "copy": "Most views update whenever the underlying slate inputs, odds snapshots, or model data are refreshed in the app workflow.",
            "items": [
                ("Daily board", "Refresh after odds pulls or lineup edits."),
                ("Drivers", "Updates with the current day slate and ratings."),
                ("Season outlook", "Updates from latest ratings and stored schedule/results."),
            ],
        },
        {
            "badge": "TB",
            "title": "How to use each tab",
            "copy": "Each workspace has a specific job so the app stays fast to scan on game day.",
            "items": [
                ("Daily Board", "Scan side and total signals across the slate."),
                ("Drivers", "See which pitchers, lineups, and bullpens are moving the board."),
                ("Season Projections", "Read the bigger-picture playoff and win outlook."),
            ],
        },
        {
            "badge": "SG",
            "title": "Signals glossary",
            "copy": "The app keeps betting language short so you can move from model view to betting decision quickly.",
            "items": [
                ("Edge", "Model probability minus no-vig market probability."),
                ("EV", "Expected value of the bet at the current price."),
                ("Best Bet", "A stronger signal when both edge and EV clear the working thresholds."),
            ],
        },
        {
            "badge": "TH",
            "title": "Current thresholds",
            "copy": "Side recommendations use the same simple signal framework throughout the product.",
            "items": [
                ("Lean", f"At least {LEAN_BET_EDGE_THRESHOLD:.1f}% edge and {LEAN_BET_EV_THRESHOLD:.1%} EV."),
                ("Strong", f"At least {STRONG_BET_EDGE_THRESHOLD:.1f}% edge and {STRONG_BET_EV_THRESHOLD:.1%} EV."),
                ("Backtest guardrail", "Season backtests only place bets at 3.0% edge or better."),
            ],
        },
    ]

    cards_html = ['<div class="about-grid">']
    for block in blocks:
        mini_blocks_html = []
        for title, copy_text in block["items"]:
            mini_blocks_html.append(
                dedent(
                    f"""
                    <div class="about-mini-block">
                        <div class="about-mini-title">{escape(str(title))}</div>
                        <div class="about-mini-copy">{escape(str(copy_text))}</div>
                    </div>
                    """
                ).strip()
            )

        cards_html.append(
            dedent(
                f"""
                <div class="about-card">
                    <div class="about-card-topline">
                        <div class="about-badge">{escape(str(block["badge"]))}</div>
                        <div class="about-card-title">{escape(str(block["title"]))}</div>
                    </div>
                    <div class="about-card-copy">{escape(str(block["copy"]))}</div>
                    <div class="about-card-blocks">
                        {''.join(mini_blocks_html)}
                    </div>
                </div>
                """
            ).strip()
        )
    cards_html.append("</div>")
    st.markdown("".join(cards_html), unsafe_allow_html=True)


def render_season_monitor(
    team_ratings_df,
    pitcher_ratings_df=None,
    hitter_ratings_df=None,
    projected_lineups_df=None,
    daily_board_inputs=None,
):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-label">Season Monitor</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-subtitle">Pitchers, lineups, bullpens, drivers.</div>',
        unsafe_allow_html=True,
    )

    if team_ratings_df is None or team_ratings_df.empty:
        st.info("Team ratings are not available yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    pitcher_watch_df, today_pitchers_df = build_pitcher_watch(pitcher_ratings_df, daily_board_inputs)
    lineup_monitor_df = build_lineup_monitor(team_ratings_df, hitter_ratings_df, projected_lineups_df)
    bullpen_leaders_df, bullpen_stress_df = build_bullpen_monitor(team_ratings_df)
    model_movers_df = build_model_movers(team_ratings_df)
    _render_driver_tab_styles()

    st.markdown(
        """
        <div class="monitor-hero">
            <div class="monitor-kicker">Drivers Workspace</div>
            <div class="monitor-title">Top slate signals behind today’s board</div>
            <div class="monitor-copy">
                Start with the strongest board-shaping edges, then scan the pitchers, lineups, bullpens, and team identities driving the model.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="drivers-toolbar-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="monitor-toolbar-topline">
            <div>
                <div class="monitor-toolbar-kicker">Workspace scope</div>
                <div class="monitor-toolbar-title">League view</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">Scope</div>', unsafe_allow_html=True)
    league_filter = st.radio(
        "Monitor Scope",
        SEASON_MONITOR_LEAGUE_OPTIONS,
        key="season_monitor_league_filter",
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("</div></div>", unsafe_allow_html=True)

    impact_inputs = daily_board_inputs.copy() if daily_board_inputs is not None else None
    if impact_inputs is not None and not impact_inputs.empty and league_filter in {"AL", "NL"}:
        league_teams = {
            team_name for team_name, division_name in TEAM_TO_DIVISION.items() if division_name.startswith(league_filter)
        }
        impact_inputs = impact_inputs.loc[
            impact_inputs["Away"].isin(league_teams) | impact_inputs["Home"].isin(league_teams)
        ].copy()

    top_n = 5
    pitcher_watch_view = _slice_monitor_dataframe(pitcher_watch_df, 8)
    today_pitchers_view = _slice_monitor_dataframe(today_pitchers_df, top_n)
    lineup_monitor_view = _slice_monitor_dataframe(
        _filter_monitor_dataframe(lineup_monitor_df, league_filter),
        8,
    )
    bullpen_leaders_view = _slice_monitor_dataframe(
        _filter_monitor_dataframe(bullpen_leaders_df, league_filter),
        top_n,
    )
    bullpen_stress_view = _slice_monitor_dataframe(
        _filter_monitor_dataframe(bullpen_stress_df, league_filter),
        top_n,
    )
    model_movers_view = _slice_monitor_dataframe(
        _filter_monitor_dataframe(model_movers_df, league_filter),
        8,
    )

    top_driver_cards = build_today_impact(impact_inputs, bullpen_stress_df)
    if not model_movers_view.empty:
        top_profile_row = model_movers_view.iloc[0]
        top_driver_cards.append(
            {
                "label": "Team Profile",
                "headline": "Best Overall Team Profile",
                "team": str(top_profile_row["Team"]),
                "metric": str(top_profile_row["Model Driver"]),
                "note": _get_driver_note("profile", top_profile_row),
            }
        )
    if len(top_driver_cards) < 4 and not today_pitchers_view.empty:
        top_pitcher_row = today_pitchers_view.iloc[0]
        top_driver_cards.append(
            {
                "label": "Starter Board",
                "headline": "Top Arm On The Slate",
                "team": str(top_pitcher_row["Pitcher"]),
                "metric": f"Score {_format_driver_decimal(top_pitcher_row['Pitcher Score'])}",
                "note": f"{top_pitcher_row['Team']} | {top_pitcher_row['Matchup']}",
            }
        )
    if len(top_driver_cards) < 4 and not lineup_monitor_view.empty:
        top_lineup_row = lineup_monitor_view.iloc[0]
        top_driver_cards.append(
            {
                "label": "Lineup Board",
                "headline": "Strongest Overall Lineup",
                "team": str(top_lineup_row["Team"]),
                "metric": f"Score {_format_driver_decimal(top_lineup_row['Lineup Score'])}",
                "note": f"Adj {_format_driver_decimal(top_lineup_row['Lineup Adjustment'])} | {top_lineup_row['Lineup Confidence']}",
            }
        )
    if len(top_driver_cards) < 4 and not bullpen_stress_view.empty:
        top_stress_row = bullpen_stress_view.iloc[0]
        top_driver_cards.append(
            {
                "label": "Bullpen Board",
                "headline": "Most Pressured Relief Group",
                "team": str(top_stress_row["Team"]),
                "metric": _get_bullpen_display_status(top_stress_row["Bullpen Status"]),
                "note": f"Fatigue {_format_driver_decimal(top_stress_row['Fatigue Penalty'])} | IP {_format_driver_decimal(top_stress_row['Relief IP Last 3'], digits=1)}",
            }
        )

    st.markdown('<div class="drivers-workspace-shell">', unsafe_allow_html=True)

    st.markdown('<div class="driver-section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="driver-card-eyebrow">Primary</div>
        <div class="driver-section-heading"><div class="driver-section-icon">🧠</div><div class="driver-section-title">Top Drivers Today</div></div>
        <div class="driver-section-copy">The clearest slate-wide signals worth reading before you dive into team-level detail.</div>
        """,
        unsafe_allow_html=True,
    )
    _render_driver_insight_cards(top_driver_cards[:4])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="driver-section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="driver-card-eyebrow">Secondary</div>
        <div class="driver-section-heading"><div class="driver-section-icon">⚾</div><div class="driver-section-title">Today’s Starting Pitchers</div></div>
        <div class="driver-section-copy">The top arms shaping today’s slate, ranked for quick read quality.</div>
        """,
        unsafe_allow_html=True,
    )
    _render_pitcher_rank_cards(today_pitchers_view, max_rows=top_n)
    st.markdown('<div class="driver-subtle-note">Pitcher Watch keeps a lighter league reference below the live slate leaders.</div>', unsafe_allow_html=True)
    _render_driver_table(
        pitcher_watch_view,
        ["Rank", "Pitcher", "Pitcher Score", "FIP", "Throws"],
        formatters={
            "Rank": lambda value: f"#{int(value)}",
            "Pitcher Score": lambda value: f"{float(value):.2f}",
            "FIP": lambda value: f"{float(value):.2f}",
            "Throws": lambda value: _format_driver_hand(value),
        },
        max_rows=8,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="driver-section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="driver-card-eyebrow">Secondary</div>
        <div class="driver-section-heading"><div class="driver-section-icon">🧢</div><div class="driver-section-title">Lineup Strength</div></div>
        <div class="driver-section-copy">The offenses most likely to move a game before market nuance takes over.</div>
        """,
        unsafe_allow_html=True,
    )
    _render_compact_rank_rows(
        lineup_monitor_view,
        [
            {"column": "Lineup Score", "label": "Lineup Score", "formatter": lambda value: _format_driver_decimal(value)},
            {"column": "Lineup Adjustment", "label": "Adjustment", "formatter": lambda value: _format_driver_decimal(value)},
            {"column": "Lineup Confidence", "label": "Confidence", "formatter": lambda value: str(value)},
        ],
        max_rows=8,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="driver-section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="driver-card-eyebrow">Tertiary</div>
        <div class="driver-section-heading"><div class="driver-section-icon">🔄</div><div class="driver-section-title">Bullpen Signals</div></div>
        <div class="driver-section-copy">A clean side-by-side read on the best relief groups and the units carrying the most stress.</div>
        """,
        unsafe_allow_html=True,
    )
    _render_bullpen_signal_board(bullpen_leaders_view, bullpen_stress_view, max_rows=top_n)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="driver-section-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="driver-card-eyebrow">Tertiary</div>
        <div class="driver-section-heading"><div class="driver-section-icon">🧠</div><div class="driver-section-title">Model Movers</div></div>
        <div class="driver-section-copy">Read this as a team identity board, with the profile label doing the heavy lifting and the support metrics kept light.</div>
        """,
        unsafe_allow_html=True,
    )
    _render_model_identity_cards(model_movers_view, max_rows=8)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('</div></div>', unsafe_allow_html=True)


def render_current_standings(team_ratings_df):
    _render_projection_workspace_styles()
    st.markdown('<div class="projection-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="projection-hero">
            <div class="projection-kicker">Season Projections</div>
            <div class="projection-title">Season Outlook</div>
            <div class="projection-copy">
                Read the season as an analytics product instead of a standings dump. Current records come from stored results, while projected wins and playoff odds update from team ratings, remaining schedule, and home-field edge.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    standings_df = build_current_division_standings(team_ratings_df)
    if standings_df.empty:
        st.markdown(
            """
            <div class="projection-surface">
                <div class="projection-section-title">Season Outlook</div>
                <div class="projection-section-copy">Projected standings will appear once current-season results and team ratings are available.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_projection_coming_soon()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    playoff_odds_df = simulate_playoff_odds(team_ratings_df)
    if not playoff_odds_df.empty:
        standings_df = standings_df.merge(playoff_odds_df, on="Team", how="left")
    else:
        standings_df["Division Odds"] = 0.0
        standings_df["Wildcard Odds"] = 0.0
        standings_df["Playoff Odds"] = 0.0

    wildcard_df = build_wildcard_standings(standings_df)
    if not wildcard_df.empty:
        wildcard_df["Cutline Trend"] = wildcard_df.apply(_build_cutline_trend, axis=1)
    playoff_summary = build_playoff_outlook_summary(standings_df, wildcard_df)

    filter_value = _render_standings_filter_bar()
    filtered_standings_df, filtered_wildcard_df = _filter_standings_view(standings_df, wildcard_df, filter_value)
    if filtered_standings_df.empty:
        filtered_standings_df = standings_df.copy()
    if filtered_wildcard_df.empty:
        filtered_wildcard_df = wildcard_df.copy()

    st.markdown(
        """
        <div class="projection-surface">
            <div class="projection-section-title">Season Outlook</div>
            <div class="projection-section-copy">Four quick reads that tell you who owns the board, who projects best, and where the pressure points sit.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_projection_summary_cards(_build_projection_summary_cards(filtered_standings_df))

    st.markdown(
        """
        <div class="projection-surface">
            <div class="projection-section-title">Team Tiers</div>
            <div class="projection-section-copy">Grouped for scanability so you can move from contenders to long shots without parsing a dense league table.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_team_tiers(_build_team_tiers(filtered_standings_df))

    st.markdown(
        """
        <div class="projection-surface">
            <div class="projection-section-title">Projected Standings</div>
            <div class="projection-section-copy">A lighter standings table with the record, projected wins, and postseason path doing most of the work.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_projection_table(filtered_standings_df)

    if playoff_summary is not None:
        race_scope_df = filtered_standings_df.copy()
        race_wildcard_df = filtered_wildcard_df.copy()
        race_summary = build_playoff_outlook_summary(race_scope_df, race_wildcard_df)
        if race_summary is not None:
            st.markdown(
                """
                <div class="projection-surface">
                    <div class="projection-section-title">Race Snapshot</div>
                    <div class="projection-section-copy">Quick league-level context for division leaders, wild card line holders, and the current bubble teams.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for league_name in LEAGUE_ORDER:
                league_leaders = race_summary["division_leaders"].loc[
                    race_summary["division_leaders"]["League"] == league_name
                ].copy()
                league_wildcard = race_summary["wildcard_leaders"].loc[
                    race_summary["wildcard_leaders"]["League"] == league_name
                ].copy()
                league_bubble = race_summary["bubble_teams"].loc[
                    race_summary["bubble_teams"]["League"] == league_name
                ].copy()
                if league_leaders.empty and league_wildcard.empty and league_bubble.empty:
                    continue
                _render_standings_race_cards(
                    league_name,
                    league_leaders,
                    league_wildcard,
                    league_bubble,
                )

    st.markdown(
        """
        <div class="projection-surface">
            <div class="projection-section-title">Next Up</div>
            <div class="projection-section-copy">Intentional placeholders for the next layer of season analytics, designed to feel like roadmap cards instead of empty states.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_projection_coming_soon()
    st.markdown("</div>", unsafe_allow_html=True)


def render_settings_about():
    _render_projection_workspace_styles()
    st.markdown(
        """
        <div class="about-hero">
            <div class="about-kicker">About The Product</div>
            <div class="about-title">MLB Win Probability Board</div>
            <div class="about-copy">
                A probability-first MLB betting workspace built to turn model output, market pricing, and game-day context into a cleaner betting read.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="about-surface">
            <div class="about-section-title">How to read the app</div>
            <div class="about-section-copy">Compact product notes for what powers each view, when it refreshes, and what the core betting signals actually mean.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_about_cards()
