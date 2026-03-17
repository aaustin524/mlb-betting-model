from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from project_config import DB_PATH


# Blending keeps the model anchored to the long-run baseline while still reacting
# to recent form. Lower baseline weight makes ratings move faster; higher baseline
# weight keeps them more stable.
DEFAULT_BASELINE_WEIGHT = 0.70
DEFAULT_RECENT_WEIGHT = 0.30
DEFAULT_OFFENSE_LOOKBACK_GAMES = 14
DEFAULT_BULLPEN_LOOKBACK_GAMES = 10
DEFAULT_OPPONENT_PITCHING_WEIGHT = 0.60
DEFAULT_OPPONENT_BULLPEN_WEIGHT = 0.40
MAX_RECENT_ADJUSTMENT = 0.15


# The historical ingest script may only store team ids in the games table. This
# mapping keeps the rolling updater compatible with the current teams.csv names.
MLB_TEAM_ID_TO_NAME = {
    108: "Los Angeles Angels",
    109: "Arizona Diamondbacks",
    110: "Baltimore Orioles",
    111: "Boston Red Sox",
    112: "Chicago Cubs",
    113: "Cincinnati Reds",
    114: "Cleveland Guardians",
    115: "Colorado Rockies",
    116: "Detroit Tigers",
    117: "Houston Astros",
    118: "Kansas City Royals",
    119: "Los Angeles Dodgers",
    120: "Washington Nationals",
    121: "New York Mets",
    133: "Athletics",
    134: "Pittsburgh Pirates",
    135: "San Diego Padres",
    136: "Seattle Mariners",
    137: "San Francisco Giants",
    138: "St. Louis Cardinals",
    139: "Tampa Bay Rays",
    140: "Texas Rangers",
    141: "Toronto Blue Jays",
    142: "Minnesota Twins",
    143: "Philadelphia Phillies",
    144: "Atlanta Braves",
    145: "Chicago White Sox",
    146: "Miami Marlins",
    147: "New York Yankees",
    158: "Milwaukee Brewers",
}


REQUIRED_TEAM_COLUMNS = [
    "team",
    "offense_vs_rhp",
    "offense_vs_lhp",
    "pitching",
    "bullpen",
]


# Rating scale assumption:
# - team offense, pitching, and bullpen values are multiplier-style ratings centered
#   near 1.00
# - for offense: values above 1.00 are stronger
# - for run prevention inputs like pitching and bullpen: values below 1.00 are better
#
# The rolling updates below assume recent performance factors are already on that
# same approximate multiplier scale. If the project later switches to a different
# rating scale, transform the recent factor into the baseline scale before blending.


def load_baseline_team_ratings(file_path: str | Path = "data/teams.csv") -> pd.DataFrame:
    baseline_df = pd.read_csv(file_path)

    for column_name in REQUIRED_TEAM_COLUMNS:
        if column_name not in baseline_df.columns:
            raise ValueError(f"teams file is missing required column: {column_name}")

    return baseline_df.copy()


def _load_completed_games(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    db_path = Path(db_path)
    if not db_path.exists():
        return pd.DataFrame()

    query = """
        SELECT
            game_date,
            home_team_id,
            away_team_id,
            home_score,
            away_score
        FROM games
        WHERE home_score IS NOT NULL
          AND away_score IS NOT NULL
        ORDER BY game_date
    """

    with sqlite3.connect(db_path) as connection:
        games_df = pd.read_sql_query(query, connection)

    if games_df.empty:
        return games_df

    games_df["game_date"] = pd.to_datetime(games_df["game_date"], errors="coerce")
    games_df = games_df.dropna(subset=["game_date", "home_score", "away_score"])
    return games_df


def _build_team_game_log(games_df: pd.DataFrame) -> pd.DataFrame:
    if games_df.empty:
        return pd.DataFrame(
            columns=[
                "team",
                "opponent_team",
                "game_date",
                "runs_scored",
                "runs_allowed",
            ]
        )

    home_games = games_df.rename(
        columns={
            "home_team_id": "team_id",
            "away_team_id": "opponent_team_id",
            "home_score": "runs_scored",
            "away_score": "runs_allowed",
        }
    )[["team_id", "opponent_team_id", "game_date", "runs_scored", "runs_allowed"]]

    away_games = games_df.rename(
        columns={
            "away_team_id": "team_id",
            "home_team_id": "opponent_team_id",
            "away_score": "runs_scored",
            "home_score": "runs_allowed",
        }
    )[["team_id", "opponent_team_id", "game_date", "runs_scored", "runs_allowed"]]

    team_games = pd.concat([home_games, away_games], ignore_index=True)
    team_games["team"] = team_games["team_id"].map(MLB_TEAM_ID_TO_NAME)
    team_games["opponent_team"] = team_games["opponent_team_id"].map(MLB_TEAM_ID_TO_NAME)
    team_games = team_games.dropna(subset=["team"]).copy()
    team_games["runs_scored"] = pd.to_numeric(team_games["runs_scored"], errors="coerce")
    team_games["runs_allowed"] = pd.to_numeric(team_games["runs_allowed"], errors="coerce")
    team_games = team_games.dropna(subset=["runs_scored", "runs_allowed"])
    return team_games.sort_values(["team", "game_date"]).reset_index(drop=True)


def _recent_team_factor(
    team_games: pd.DataFrame,
    stat_column: str,
    lookback_games: int,
) -> pd.Series:
    if team_games.empty:
        return pd.Series(dtype=float)

    recent_games = (
        team_games.groupby("team", group_keys=False)
        .tail(lookback_games)
        .copy()
    )
    league_average = recent_games[stat_column].mean()
    if pd.isna(league_average) or league_average <= 0:
        return pd.Series(dtype=float)

    team_average = recent_games.groupby("team")[stat_column].mean()
    return team_average / league_average


def _build_recent_offense_factor(
    team_games: pd.DataFrame,
    baseline_df: pd.DataFrame,
    lookback_games: int,
    opponent_pitching_weight: float,
    opponent_bullpen_weight: float,
) -> pd.Series:
    """
    Build a lightweight wRC-style recent offense proxy.

    Raw runs scored are noisy because they depend on opponent quality and game context.
    To reduce that noise, we scale each game by a simple opponent run-prevention proxy
    built from the opponent's baseline pitching and bullpen ratings.

    This is not full wRC+:
    - it does not use park-adjusted linear weights
    - it does not separate starter and bullpen faced within the actual game
    - it does not yet split by opposing pitcher handedness

    It is still useful because it moves recent offense toward a cleaner "how well did a
    team score relative to the run-prevention quality it faced?" signal.
    """
    if team_games.empty:
        return pd.Series(dtype=float)

    recent_games = (
        team_games.groupby("team", group_keys=False)
        .tail(lookback_games)
        .copy()
    )
    if recent_games.empty:
        return pd.Series(dtype=float)

    opponent_lookup = baseline_df.set_index("team")[["pitching", "bullpen"]]
    recent_games = recent_games.merge(
        opponent_lookup,
        left_on="opponent_team",
        right_index=True,
        how="left",
    )
    recent_games["opponent_run_prevention"] = (
        recent_games["pitching"] * opponent_pitching_weight
        + recent_games["bullpen"] * opponent_bullpen_weight
    )
    recent_games["adjusted_offense_value"] = recent_games["runs_scored"] / recent_games["opponent_run_prevention"]
    recent_games = recent_games.replace([float("inf"), float("-inf")], pd.NA)
    recent_games = recent_games.dropna(subset=["adjusted_offense_value"])

    if recent_games.empty:
        return pd.Series(dtype=float)

    league_average = recent_games["adjusted_offense_value"].mean()
    if pd.isna(league_average) or league_average <= 0:
        return pd.Series(dtype=float)

    team_average = recent_games.groupby("team")["adjusted_offense_value"].mean()
    return team_average / league_average


def build_rolling_team_ratings(
    baseline_path: str | Path = "data/teams.csv",
    db_path: str | Path = DB_PATH,
    baseline_weight: float = DEFAULT_BASELINE_WEIGHT,
    recent_weight: float = DEFAULT_RECENT_WEIGHT,
    offense_lookback_games: int = DEFAULT_OFFENSE_LOOKBACK_GAMES,
    bullpen_lookback_games: int = DEFAULT_BULLPEN_LOOKBACK_GAMES,
) -> pd.DataFrame:
    """
    Blend stable baseline team ratings with recent team form.

    Why this helps:
    - MLB teams change over the season due to injuries, roster churn, and hot/cold streaks.
    - Recent scoring and run prevention give the model a lightweight daily update signal.

    Why blending is safer:
    - Using only recent form can overreact to small samples and noisy baseball outcomes.
    - Blending keeps the long-run baseline in place while letting recent games matter.

    Tuning guidance:
    - Increase recent_weight to react faster to form changes.
    - Increase baseline_weight to keep ratings steadier.
    - Shorter lookbacks make updates faster but noisier.
    - Longer lookbacks make updates slower but more stable.
    """
    if baseline_weight < 0 or recent_weight < 0:
        raise ValueError("baseline_weight and recent_weight must be non-negative")

    total_weight = baseline_weight + recent_weight
    if total_weight <= 0:
        raise ValueError("baseline_weight + recent_weight must be greater than 0")

    baseline_weight = baseline_weight / total_weight
    recent_weight = recent_weight / total_weight

    baseline_df = load_baseline_team_ratings(baseline_path)
    games_df = _load_completed_games(db_path)
    team_games = _build_team_game_log(games_df)

    if team_games.empty:
        return baseline_df.copy()

    offense_factor = _build_recent_offense_factor(
        team_games=team_games,
        baseline_df=baseline_df,
        lookback_games=offense_lookback_games,
        opponent_pitching_weight=DEFAULT_OPPONENT_PITCHING_WEIGHT,
        opponent_bullpen_weight=DEFAULT_OPPONENT_BULLPEN_WEIGHT,
    )

    # Recent offense is not yet split by opposing pitcher hand. For now we use the
    # same recent scoring factor to nudge both offense_vs_rhp and offense_vs_lhp.
    # That keeps the current app/model interface intact while we wait for richer
    # handedness-specific game logs.

    # Until the project ingests bullpen-only run prevention, recent runs allowed is
    # a simple proxy for team run prevention. This is directionally compatible with
    # the current bullpen scale because lower ratings represent better prevention
    # and lower recent runs allowed also produce a factor below 1.00. If bullpen is
    # ever redefined so higher values mean better quality, this factor should be
    # inverted before blending.
    bullpen_factor = _recent_team_factor(
        team_games=team_games,
        stat_column="runs_allowed",
        lookback_games=bullpen_lookback_games,
    )

    updated_df = baseline_df.copy()

    def blend_rating(team_name: str, baseline_value: float, factor_series: pd.Series) -> float:
        recent_factor = factor_series.get(team_name)
        if recent_factor is None or pd.isna(recent_factor):
            return round(float(baseline_value), 3)
        baseline_value = float(baseline_value)
        recent_adjustment = (float(recent_factor) - 1.0) * recent_weight
        recent_adjustment = max(-MAX_RECENT_ADJUSTMENT, min(MAX_RECENT_ADJUSTMENT, recent_adjustment))
        # Apply recent form as a controlled multiplier-style adjustment around 1.00
        # so the updated rating stays on the same scale as the baseline file.
        blended_rating = baseline_value * (1.0 + recent_adjustment)
        return round(blended_rating, 3)

    # Recent offense is still not split by opposing pitcher hand, so the same
    # opponent-adjusted offense factor is currently applied to both split columns.
    updated_df["offense_vs_rhp"] = updated_df.apply(
        lambda row: blend_rating(row["team"], row["offense_vs_rhp"], offense_factor),
        axis=1,
    )
    updated_df["offense_vs_lhp"] = updated_df.apply(
        lambda row: blend_rating(row["team"], row["offense_vs_lhp"], offense_factor),
        axis=1,
    )
    updated_df["bullpen"] = updated_df.apply(
        lambda row: blend_rating(row["team"], row["bullpen"], bullpen_factor),
        axis=1,
    )

    return updated_df.copy()


def update_team_ratings_file(
    baseline_path: str | Path = "data/teams.csv",
    output_path: str | Path | None = None,
    db_path: str | Path = DB_PATH,
    baseline_weight: float = DEFAULT_BASELINE_WEIGHT,
    recent_weight: float = DEFAULT_RECENT_WEIGHT,
    offense_lookback_games: int = DEFAULT_OFFENSE_LOOKBACK_GAMES,
    bullpen_lookback_games: int = DEFAULT_BULLPEN_LOOKBACK_GAMES,
) -> pd.DataFrame:
    updated_df = build_rolling_team_ratings(
        baseline_path=baseline_path,
        db_path=db_path,
        baseline_weight=baseline_weight,
        recent_weight=recent_weight,
        offense_lookback_games=offense_lookback_games,
        bullpen_lookback_games=bullpen_lookback_games,
    )

    destination = Path(output_path) if output_path is not None else Path(baseline_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    updated_df.to_csv(destination, index=False)
    return updated_df
