"""Season Monitor leaderboard and standings rendering helpers."""

from __future__ import annotations

import math
import sqlite3
from html import escape
from textwrap import dedent

import numpy as np
import pandas as pd
import streamlit as st

from model.bullpen_usage import estimate_bullpen_fatigue, load_recent_bullpen_usage
from model.lineup_strength import calculate_lineup_adjustment
from model.rolling_team_ratings import MLB_TEAM_ID_TO_NAME
from project_config import DB_PATH

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


@st.cache_data(show_spinner=False)
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


@st.cache_data(show_spinner=False)
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
    standings_df["Win %"] = (
        standings_df["Actual Wins"] / standings_df["Games Played"].replace({0: pd.NA})
    ).fillna(0.0)
    total_games_projection = (standings_df["Projected Wins"] + standings_df["Projected Losses"]).replace({0: pd.NA})
    standings_df["Projected Win %"] = (standings_df["Projected Wins"] / total_games_projection).fillna(0.0)
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


@st.cache_data(show_spinner=False)
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


def _filter_monitor_team(dataframe, team_filter):
    if dataframe is None or dataframe.empty or team_filter == "All Teams":
        return dataframe
    if "Team" not in dataframe.columns:
        return dataframe
    return dataframe.loc[dataframe["Team"] == team_filter].reset_index(drop=True)


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
    movers_df["Offense Edge"] = movers_df["Offense Score"] - movers_df[["Pitching Score", "Bullpen Score"]].mean(axis=1)
    movers_df["Run Prevention Edge"] = (
        movers_df[["Pitching Score", "Bullpen Score"]].mean(axis=1) - movers_df["Offense Score"]
    )
    movers_df["Model Driver"] = np.where(
        movers_df["Offense Edge"] >= 0.04,
        "Offense Driven",
        np.where(movers_df["Run Prevention Edge"] >= 0.04, "Run Prevention Driven", "Balanced"),
    )
    movers_df["Volatility Score"] = (
        movers_df[["Offense Score", "Pitching Score", "Bullpen Score"]].max(axis=1)
        - movers_df[["Offense Score", "Pitching Score", "Bullpen Score"]].min(axis=1)
    ).round(3)
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
        cards.append(
            {
                "label": "Biggest Starter Edge",
                "team": str(top_row["Starter Edge Team"]),
                "value": f"{float(top_row['Starter Edge']):.3f} | {top_row['Matchup']}",
            }
        )

    lineup_df = impact_df.dropna(subset=["Lineup Boost"]).sort_values(by="Lineup Boost", ascending=False)
    if not lineup_df.empty:
        top_row = lineup_df.iloc[0]
        cards.append(
            {
                "label": "Biggest Lineup Boost",
                "team": str(top_row["Lineup Boost Team"]),
                "value": f"Adj {float(top_row['Lineup Boost']):.3f} | {top_row['Matchup']}",
            }
        )

    bullpen_df = impact_df.dropna(subset=["Bullpen Risk"]).sort_values(by="Bullpen Risk", ascending=False)
    if not bullpen_df.empty:
        top_row = bullpen_df.iloc[0]
        cards.append(
            {
                "label": "Biggest Bullpen Risk",
                "team": str(top_row["Bullpen Risk Team"]),
                "value": f"{top_row['Bullpen Status']} | {top_row['Matchup']}",
            }
        )

    if not starter_df.empty and not bullpen_df.empty:
        combo_df = impact_df.dropna(subset=["Starter Edge", "Bullpen Risk"]).copy()
        combo_df["Pressure Score"] = combo_df["Starter Edge"] + combo_df["Bullpen Risk"]
        combo_df = combo_df.sort_values(by="Pressure Score", ascending=False)
        if not combo_df.empty:
            top_row = combo_df.iloc[0]
            cards.append(
                {
                    "label": "Best Unit Mismatch",
                    "team": str(top_row["Starter Edge Team"]),
                    "value": f"{top_row['Matchup']} | Pressure {float(top_row['Pressure Score']):.3f}",
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


def _render_monitor_active_filters(league_filter, table_view, team_filter, row_limit):
    filter_items = [
        ("Scope", league_filter),
        ("Rows", "All" if row_limit is None else str(row_limit)),
        ("Team", team_filter if team_filter != "All Teams" else "All clubs"),
        ("View", table_view),
    ]
    chips = "".join(
        f'<span class="monitor-filter-pill"><span class="monitor-filter-pill-label">{escape(label)}</span>{escape(value)}</span>'
        for label, value in filter_items
    )
    st.markdown(f'<div class="monitor-filter-pill-row">{chips}</div>', unsafe_allow_html=True)


def _resolve_monitor_team_filter(team_filter_options):
    search_value = st.text_input(
        "Team Lookup",
        key="season_monitor_team_search",
        value=st.session_state.get("season_monitor_team_search", ""),
        placeholder="Search team or leave blank",
        label_visibility="collapsed",
    ).strip()

    if not search_value:
        return "All Teams"

    normalized_search = search_value.lower()
    exact_match = next((team for team in team_filter_options if team.lower() == normalized_search), None)
    if exact_match:
        return exact_match

    partial_match = next((team for team in team_filter_options if normalized_search in team.lower()), None)
    if partial_match:
        return partial_match

    return "All Teams"


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
    if not team_name or team_name == "All Teams":
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

    ratings_df = team_ratings_df.reset_index().rename(columns={"team": "Team"}).copy()
    ratings_df["Avg Offense"] = (ratings_df["offense_vs_rhp"] + ratings_df["offense_vs_lhp"]) / 2.0

    ratings_df["Overall Rating"] = (
        ratings_df["offense_vs_rhp"] + ratings_df["offense_vs_lhp"] - ratings_df["bullpen"]
    )
    ratings_df["Power Score"] = (
        ratings_df["Avg Offense"] + (1.0 - ratings_df["pitching"]) + (1.0 - ratings_df["bullpen"])
    )
    ratings_df["Pitching Score"] = (1.0 - ratings_df["pitching"]) + (1.0 - ratings_df["bullpen"])

    strength_rankings_df = (
        ratings_df[["Team", "Overall Rating", "offense_vs_rhp", "offense_vs_lhp", "pitching", "bullpen"]]
        .sort_values(by=["Overall Rating", "offense_vs_rhp", "offense_vs_lhp"], ascending=[False, False, False])
    )
    strength_rankings_df = _add_rank_column(
        strength_rankings_df.rename(
            columns={
                "offense_vs_rhp": "Off vs RHP",
                "offense_vs_lhp": "Off vs LHP",
                "pitching": "Starter Rating",
                "bullpen": "Bullpen Rating",
            }
        )
    )

    offenses_df = (
        ratings_df[["Team", "offense_vs_rhp", "offense_vs_lhp", "Avg Offense"]]
        .sort_values(by=["Avg Offense", "offense_vs_rhp", "offense_vs_lhp"], ascending=[False, False, False])
    )
    offenses_df = _add_rank_column(
        offenses_df.rename(
            columns={
                "offense_vs_rhp": "Off vs RHP",
                "offense_vs_lhp": "Off vs LHP",
                "Avg Offense": "Offense Score",
            }
        )
    )

    pitching_df = (
        ratings_df[["Team", "pitching", "bullpen", "Pitching Score"]]
        .rename(columns={"pitching": "Starter Strength", "bullpen": "Bullpen Rating"})
        .sort_values(by=["Starter Strength", "Bullpen Rating"], ascending=[True, True])
    )
    pitching_df["Staff Score"] = (1.0 / pitching_df["Starter Strength"]) + (1.0 / pitching_df["Bullpen Rating"])
    pitching_df = _add_rank_column(pitching_df[["Team", "Staff Score", "Starter Strength", "Bullpen Rating"]])

    bullpen_df = (
        ratings_df[["Team", "bullpen"]]
        .rename(columns={"bullpen": "Bullpen Rating"})
        .sort_values(by=["Bullpen Rating"], ascending=[True])
    )
    bullpen_df["Bullpen Score"] = 1.0 / bullpen_df["Bullpen Rating"]
    bullpen_df = _add_rank_column(bullpen_df[["Team", "Bullpen Score", "Bullpen Rating"]])

    power_rankings_df = (
        ratings_df[["Team", "Power Score", "Avg Offense", "pitching", "bullpen"]]
        .rename(columns={"pitching": "Starter Strength", "bullpen": "Bullpen Rating"})
        .sort_values(by=["Power Score", "Avg Offense"], ascending=[False, False])
    )
    power_rankings_df = _add_rank_column(power_rankings_df.rename(columns={"Avg Offense": "Offense Score"}))
    projected_standings_df = build_projected_standings(team_ratings_df)
    pitcher_watch_df, today_pitchers_df = build_pitcher_watch(pitcher_ratings_df, daily_board_inputs)
    lineup_monitor_df = build_lineup_monitor(team_ratings_df, hitter_ratings_df, projected_lineups_df)
    bullpen_leaders_df, bullpen_stress_df = build_bullpen_monitor(team_ratings_df)
    model_movers_df = build_model_movers(team_ratings_df)

    best_projected_row = projected_standings_df.iloc[0]
    best_offense_row = offenses_df.iloc[0]
    best_pitching_row = pitching_df.iloc[0]
    best_bullpen_row = bullpen_df.iloc[0]

    st.markdown(
        """
        <div class="monitor-hero">
            <div class="monitor-kicker">Season analytics</div>
            <div class="monitor-title">Driver terminal</div>
            <div class="monitor-copy">
                Premium scan of pitchers, lineups, bullpens, and team-level model pressure.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    team_filter_options = ["All Teams"] + sorted(projected_standings_df["Team"].tolist())
    st.markdown(
        """
        <div class="monitor-toolbar-shell">
            <div class="monitor-toolbar-topline">
                <div>
                    <div class="monitor-toolbar-kicker">Driver controls</div>
                    <div class="monitor-toolbar-title">Scope the board</div>
                </div>
                <div class="monitor-toolbar-note">Tight filters. Faster reads.</div>
            </div>
        """,
        unsafe_allow_html=True,
    )
    control_col_1, control_col_2, control_col_3 = st.columns([1.15, 1.1, 1.55])
    with control_col_1:
        st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">Scope</div>', unsafe_allow_html=True)
        league_filter = st.radio(
            "Monitor Scope",
            SEASON_MONITOR_LEAGUE_OPTIONS,
            key="season_monitor_league_filter",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with control_col_2:
        st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">Rows</div>', unsafe_allow_html=True)
        table_view = st.radio(
            "Table Size",
            SEASON_MONITOR_TABLE_OPTIONS,
            key="season_monitor_table_size",
            horizontal=True,
            label_visibility="collapsed",
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with control_col_3:
        st.markdown('<div class="monitor-toolbar-slot"><div class="monitor-toolbar-label">Team</div>', unsafe_allow_html=True)
        team_filter = _resolve_monitor_team_filter(team_filter_options)
        quick_team_options = ["All Teams"] + team_filter_options[1:3]
        quick_team_cols = st.columns(len(quick_team_options))
        for quick_col, quick_team in zip(quick_team_cols, quick_team_options):
            with quick_col:
                if st.button(
                    "All" if quick_team == "All Teams" else quick_team.split()[-1],
                    key=f"season_monitor_team_quick_{quick_team}",
                    use_container_width=True,
                ):
                    st.session_state["season_monitor_team_search"] = "" if quick_team == "All Teams" else quick_team
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    impact_inputs = daily_board_inputs.copy() if daily_board_inputs is not None else None
    if impact_inputs is not None and not impact_inputs.empty:
        if league_filter in {"AL", "NL"}:
            league_teams = {
                team_name for team_name, division_name in TEAM_TO_DIVISION.items() if division_name.startswith(league_filter)
            }
            impact_inputs = impact_inputs.loc[
                impact_inputs["Away"].isin(league_teams) | impact_inputs["Home"].isin(league_teams)
            ].copy()
        if team_filter != "All Teams":
            impact_inputs = impact_inputs.loc[
                (impact_inputs["Away"] == team_filter) | (impact_inputs["Home"] == team_filter)
            ].copy()
    today_impact_cards = build_today_impact(impact_inputs, bullpen_stress_df)

    row_limit = _get_monitor_row_limit(table_view)
    _render_monitor_active_filters(league_filter, table_view, team_filter, row_limit)
    st.markdown("</div>", unsafe_allow_html=True)
    projected_standings_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(projected_standings_df, league_filter), team_filter),
        row_limit,
    )
    power_rankings_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(power_rankings_df, league_filter), team_filter),
        row_limit,
    )
    strength_rankings_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(strength_rankings_df, league_filter), team_filter),
        row_limit,
    )
    offenses_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(offenses_df, league_filter), team_filter),
        row_limit,
    )
    pitching_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(pitching_df, league_filter), team_filter),
        row_limit,
    )
    bullpen_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(bullpen_df, league_filter), team_filter),
        row_limit,
    )
    pitcher_watch_view = _slice_monitor_dataframe(_filter_monitor_team(pitcher_watch_df, team_filter), row_limit)
    today_pitchers_view = _slice_monitor_dataframe(_filter_monitor_team(today_pitchers_df, team_filter), row_limit)
    lineup_monitor_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(lineup_monitor_df, league_filter), team_filter),
        row_limit,
    )
    bullpen_leaders_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(bullpen_leaders_df, league_filter), team_filter),
        row_limit,
    )
    bullpen_stress_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(bullpen_stress_df, league_filter), team_filter),
        row_limit,
    )
    model_movers_view = _slice_monitor_dataframe(
        _filter_monitor_team(_filter_monitor_dataframe(model_movers_df, league_filter), team_filter),
        row_limit,
    )

    if team_filter != "All Teams":
        _render_team_profile_card(
            team_filter,
            projected_standings_view,
            offenses_view,
            pitching_view if not pitching_view.empty else bullpen_leaders_view,
            bullpen_view,
            power_rankings_view,
        )

    best_pitcher_driver = _get_best_pitcher_driver_card(today_pitchers_view, pitcher_watch_view)

    _render_monitor_section_header(
        "Model Drivers",
        "Fast-read leaders",
    )
    _render_monitor_summary_cards(
        [
            {
                "label": "Strongest Team",
                "team": best_projected_row["Team"],
                "value": f"{float(best_projected_row['Projected Wins']):.1f} projected wins",
            },
            {
                "label": "Best Offense",
                "team": best_offense_row["Team"],
                "value": f"Offense score {float(best_offense_row['Offense Score']):.3f}",
            },
            {
                "label": "Best Starter Pool",
                "team": best_pitcher_driver["team"],
                "value": best_pitcher_driver["value"],
            },
            {
                "label": "Best Bullpen",
                "team": bullpen_leaders_view.iloc[0]["Team"] if not bullpen_leaders_view.empty else best_bullpen_row["Team"],
                "value": f"Bullpen score {float((bullpen_leaders_view.iloc[0] if not bullpen_leaders_view.empty else best_bullpen_row)['Bullpen Score']):.3f}",
            },
            {
                "label": "Most Stressed Pen",
                "team": bullpen_stress_view.iloc[0]["Team"] if not bullpen_stress_view.empty else best_pitching_row["Team"],
                "value": (
                    f"Fatigue {float(bullpen_stress_view.iloc[0]['Fatigue Penalty']):.3f}"
                    if not bullpen_stress_view.empty
                    else f"Staff score {float(best_pitching_row['Staff Score']):.3f}"
                ),
            },
        ]
    )
    _render_monitor_notes(
        [
            {
                "label": "Pitchers",
                "value": "Today | starter board",
            },
            {
                "label": "Lineups",
                "value": "Score | adjustment",
            },
            {
                "label": "Bullpens",
                "value": "Quality | fatigue",
            },
        ]
    )

    if today_impact_cards:
        _render_monitor_section_header(
            "Today Impact",
            "Slate snapshot",
        )
        _render_monitor_summary_cards(today_impact_cards)

    st.markdown('<div class="monitor-layout-grid">', unsafe_allow_html=True)
    with st.container():
        with st.expander("Pitcher Watch", expanded=True):
            st.markdown(
                '<div class="monitor-expander-copy">Today + season view.</div>',
                unsafe_allow_html=True,
            )
            if not today_pitchers_view.empty:
                _render_top_leader_cards(
                    today_pitchers_view,
                    value_column="Pitcher Score",
                    subtitle_builder=lambda row: f"{row['Team']} | {row['Matchup']} | {row['Throws'] or 'N/A'} hand",
                    value_format=lambda value: f"{float(value):.3f}",
                )
                _render_monitor_leaderboard_table(
                    today_pitchers_view,
                    ["Rank", "Pitcher", "Team", "Matchup", "Throws", "Pitcher Score", "Pitcher Rating", "FIP"],
                    formatters={
                        "Rank": lambda value: f"{int(value)}",
                        "Pitcher Score": lambda value: f"{float(value):.3f}",
                        "Pitcher Rating": lambda value: f"{float(value):.2f}",
                        "FIP": lambda value: f"{float(value):.2f}",
                    },
                )
            st.markdown('<div class="monitor-expander-copy">League reference.</div>', unsafe_allow_html=True)
            _render_monitor_leaderboard_table(
                pitcher_watch_view,
                ["Rank", "Pitcher", "Team", "Throws", "Pitcher Score", "Pitcher Rating", "FIP"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Pitcher Score": lambda value: f"{float(value):.3f}",
                    "Pitcher Rating": lambda value: f"{float(value):.2f}",
                    "FIP": lambda value: f"{float(value):.2f}",
                },
            )
    with st.container():
        with st.expander("Lineup Strength", expanded=(team_filter != "All Teams")):
            st.markdown(
                '<div class="monitor-expander-copy">Lineup score | confidence.</div>',
                unsafe_allow_html=True,
            )
            _render_top_leader_cards(
                lineup_monitor_view,
                value_column="Lineup Score",
                subtitle_builder=lambda row: f"Adj {float(row['Lineup Adjustment']):.3f} | Hitters {int(row['Projected Hitters'])}",
                value_format=lambda value: f"{float(value):.3f}",
            )
            _render_monitor_leaderboard_table(
                lineup_monitor_view,
                ["Rank", "Team", "Lineup Score", "Lineup Adjustment", "Offense Score", "Projected Hitters", "Lineup Confidence"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Lineup Score": lambda value: f"{float(value):.3f}",
                    "Lineup Adjustment": lambda value: f"{float(value):.3f}",
                    "Offense Score": lambda value: f"{float(value):.3f}",
                    "Projected Hitters": lambda value: f"{int(value)}",
                },
            )
    st.markdown('</div>', unsafe_allow_html=True)

    with st.expander("Bullpen Monitor", expanded=(team_filter != "All Teams")):
        st.markdown(
            '<div class="monitor-expander-copy">Quality | stress.</div>',
            unsafe_allow_html=True,
        )
        left_col, right_col = st.columns(2)
        with left_col:
            _render_top_leader_cards(
                bullpen_leaders_view,
                value_column="Bullpen Score",
                subtitle_builder=lambda row: f"Fatigue {float(row['Fatigue Penalty']):.3f} | IP last 3 {float(row['Relief IP Last 3']):.1f}",
                value_format=lambda value: f"{float(value):.3f}",
            )
            _render_monitor_leaderboard_table(
                bullpen_leaders_view,
                ["Rank", "Team", "Bullpen Score", "Bullpen Rating", "Fatigue Penalty", "Relief IP Last 3", "Bullpen Status"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Bullpen Score": lambda value: f"{float(value):.3f}",
                    "Bullpen Rating": lambda value: f"{float(value):.3f}",
                    "Fatigue Penalty": lambda value: f"{float(value):.3f}",
                    "Relief IP Last 3": lambda value: f"{float(value):.1f}",
                },
            )
        with right_col:
            _render_monitor_leaderboard_table(
                bullpen_stress_view,
                ["Rank", "Team", "Fatigue Penalty", "Relief IP Last 3", "Adjusted Bullpen", "Bullpen Score", "Bullpen Status"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Fatigue Penalty": lambda value: f"{float(value):.3f}",
                    "Relief IP Last 3": lambda value: f"{float(value):.1f}",
                    "Adjusted Bullpen": lambda value: f"{float(value):.3f}",
                    "Bullpen Score": lambda value: f"{float(value):.3f}",
                },
            )

    with st.expander("Model Movers", expanded=(team_filter != "All Teams")):
        st.markdown(
            '<div class="monitor-expander-copy">Driver mix.</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="monitor-layout-grid">', unsafe_allow_html=True)
        with st.container():
            st.markdown(
                dedent(
                    """
                    <div class="monitor-panel">
                        <div class="monitor-panel-title">Model Driver Board</div>
                        <div class="monitor-panel-copy">Offense | pitching | bullpen.</div>
                    """
                ).strip(),
                unsafe_allow_html=True,
            )
            _render_monitor_leaderboard_table(
                model_movers_view,
                ["Rank", "Team", "Model Driver", "Power Score", "Offense Score", "Pitching Score", "Bullpen Score", "Volatility Score"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Power Score": lambda value: f"{float(value):.3f}",
                    "Offense Score": lambda value: f"{float(value):.3f}",
                    "Pitching Score": lambda value: f"{float(value):.3f}",
                    "Bullpen Score": lambda value: f"{float(value):.3f}",
                    "Volatility Score": lambda value: f"{float(value):.3f}",
                },
            )
            st.markdown('</div>', unsafe_allow_html=True)
        with st.container():
            st.markdown(
                dedent(
                    """
                    <div class="monitor-panel">
                        <div class="monitor-panel-title">Team Power Reference</div>
                        <div class="monitor-panel-copy">Quick team context.</div>
                    """
                ).strip(),
                unsafe_allow_html=True,
            )
            _render_monitor_leaderboard_table(
                projected_standings_view,
                ["Rank", "Team", "Power Score", "Projected Win %", "Projected Wins", "Offense Score", "Pitching Score", "Bullpen Score"],
                formatters={
                    "Rank": lambda value: f"{int(value)}",
                    "Power Score": lambda value: f"{float(value):.3f}",
                    "Projected Win %": lambda value: f"{float(value):.3f}",
                    "Projected Wins": lambda value: f"{float(value):.1f}",
                    "Offense Score": lambda value: f"{float(value):.3f}",
                    "Pitching Score": lambda value: f"{float(value):.3f}",
                    "Bullpen Score": lambda value: f"{float(value):.3f}",
                },
            )
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


def render_current_standings(team_ratings_df):
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="monitor-hero">
            <div class="monitor-kicker">Race board</div>
            <div class="monitor-title">Division Standings and Playoff Odds</div>
            <div class="monitor-copy">
                Actual records come from SQLite game results, while projected finishes and playoff percentages update from current ratings, remaining schedule, and home-field edge.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    standings_df = build_current_division_standings(team_ratings_df)
    if standings_df.empty:
        st.info("Current season standings are not available yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    playoff_odds_df = simulate_playoff_odds(team_ratings_df)
    if not playoff_odds_df.empty:
        standings_df = standings_df.merge(playoff_odds_df, on="Team", how="left")

    wildcard_df = build_wildcard_standings(standings_df)
    if not wildcard_df.empty:
        wildcard_df["Cutline Trend"] = wildcard_df.apply(_build_cutline_trend, axis=1)
    playoff_summary = build_playoff_outlook_summary(standings_df, wildcard_df)

    filter_value = st.selectbox(
        "Standings View",
        options=STANDINGS_FILTER_OPTIONS,
        index=0,
        help="Filter the race board to all teams, a single league, or one division.",
    )
    filtered_standings_df, filtered_wildcard_df = _filter_standings_view(standings_df, wildcard_df, filter_value)

    _render_monitor_section_header(
        "Monte Carlo Playoff Odds",
        "Simulated from remaining-game outcomes using current records, remaining schedule, team ratings, and home-field edge.",
    )
    playoff_odds_preview_df = filtered_standings_df[
        ["Team", "Division Odds", "Wildcard Odds", "Playoff Odds"]
    ].sort_values(by=["Playoff Odds", "Division Odds"], ascending=[False, False]).head(10)
    st.dataframe(
        playoff_odds_preview_df.style
        .map(_style_odds_value, subset=["Division Odds"])
        .map(_style_odds_value, subset=["Wildcard Odds"])
        .map(_style_odds_value, subset=["Playoff Odds"]),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Division Odds": st.column_config.NumberColumn("Division %", format="%.1f"),
            "Wildcard Odds": st.column_config.NumberColumn("Wildcard %", format="%.1f"),
            "Playoff Odds": st.column_config.NumberColumn("Playoff %", format="%.1f"),
        },
    )

    for league_name in LEAGUE_ORDER:
        if filter_value not in {"All", league_name} and filter_value not in [division for division in DIVISION_ORDER if division.startswith(league_name)]:
            continue
        division_leader_slice = playoff_summary["division_leaders"].loc[
            playoff_summary["division_leaders"]["League"] == league_name
        ].copy()
        wildcard_slice = playoff_summary["wildcard_leaders"].loc[
            playoff_summary["wildcard_leaders"]["League"] == league_name
        ].copy()
        bubble_slice = playoff_summary["bubble_teams"].loc[
            playoff_summary["bubble_teams"]["League"] == league_name
        ].copy()

        default_open = filter_value in {"All", league_name} or filter_value in [division for division in DIVISION_ORDER if division.startswith(league_name)]
        with st.expander(f"{league_name} Race Board", expanded=default_open):
            _render_monitor_section_header(
                "Playoff Outlook",
                "League race cards to scan division leaders, wildcard line, and bubble teams quickly.",
            )
            _render_standings_race_cards(
                league_name,
                division_leader_slice,
                wildcard_slice,
                bubble_slice,
            )

            for division_name in [division for division in DIVISION_ORDER if division.startswith(league_name)]:
                division_df = filtered_standings_df.loc[filtered_standings_df["Division"] == division_name].copy()
                if division_df.empty:
                    continue

                _render_monitor_section_header(
                    division_name,
                    "Actual record, rest-of-season win expectation, and postseason path for this division.",
                )
                display_df = division_df[
                    [
                        "Division Rank",
                        "Team",
                        "Actual Wins",
                        "Actual Losses",
                        "Win %",
                        "Remaining Games",
                        "Proj Remaining Wins",
                        "Playoff Outlook",
                        "Projected Wins",
                        "Projected Losses",
                        "Projected Win %",
                        "Division Odds",
                        "Wildcard Odds",
                        "Playoff Odds",
                    ]
                ].rename(columns={"Division Rank": "Rank"})
                st.dataframe(
                    _style_standings_table(display_df),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
                        "Actual Wins": st.column_config.NumberColumn("Wins", format="%d"),
                        "Actual Losses": st.column_config.NumberColumn("Losses", format="%d"),
                        "Win %": st.column_config.NumberColumn("Win %", format="%.3f"),
                        "Remaining Games": st.column_config.NumberColumn("Remain", format="%d"),
                        "Proj Remaining Wins": st.column_config.NumberColumn("Proj ROS Wins", format="%.1f"),
                        "Projected Wins": st.column_config.NumberColumn("Proj Wins", format="%.1f"),
                        "Projected Losses": st.column_config.NumberColumn("Proj Losses", format="%.1f"),
                        "Projected Win %": st.column_config.NumberColumn("Proj Win %", format="%.3f"),
                        "Division Odds": st.column_config.NumberColumn("Division %", format="%.1f"),
                        "Wildcard Odds": st.column_config.NumberColumn("Wildcard %", format="%.1f"),
                        "Playoff Odds": st.column_config.NumberColumn("Playoff %", format="%.1f"),
                    },
                )

            league_wildcard_df = filtered_wildcard_df.loc[filtered_wildcard_df["League"] == league_name].copy()
            if not league_wildcard_df.empty:
                _render_monitor_section_header(
                    "Wildcard Race",
                    "League-level cutline table showing who projects inside, on the edge, or outside.",
                )
                wildcard_display_df = league_wildcard_df[
                    [
                        "Wildcard Rank",
                        "Team",
                        "Actual Wins",
                        "Actual Losses",
                        "Projected Wins",
                        "Projected Losses",
                        "Games Behind Cutline",
                        "Cutline Trend",
                        "Playoff Outlook",
                        "Wildcard Odds",
                        "Playoff Odds",
                    ]
                ].rename(columns={"Wildcard Rank": "Rank"})
                st.dataframe(
                    _style_standings_table(wildcard_display_df),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
                        "Actual Wins": st.column_config.NumberColumn("Wins", format="%d"),
                        "Actual Losses": st.column_config.NumberColumn("Losses", format="%d"),
                        "Projected Wins": st.column_config.NumberColumn("Proj Wins", format="%.1f"),
                        "Projected Losses": st.column_config.NumberColumn("Proj Losses", format="%.1f"),
                        "Games Behind Cutline": st.column_config.NumberColumn("GB Cutline", format="%.1f"),
                        "Wildcard Odds": st.column_config.NumberColumn("Wildcard %", format="%.1f"),
                        "Playoff Odds": st.column_config.NumberColumn("Playoff %", format="%.1f"),
                    },
                )

    st.markdown('</div>', unsafe_allow_html=True)
