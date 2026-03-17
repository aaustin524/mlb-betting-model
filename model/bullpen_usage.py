from pathlib import Path

import pandas as pd

from project_config import (
    MAX_KEY_RELIEVERS_COUNTED,
    UNAVAILABLE_RELIEVER_PENALTY,
    UNAVAILABLE_TWO_DAY_PITCHES,
    UNAVAILABLE_YESTERDAY_PITCHES,
)


RELIEVER_NAME_CANDIDATES = ["pitcher_name", "pitcher", "reliever_name", "reliever", "player_name"]
PITCH_COUNT_CANDIDATES = ["pitch_count", "pitches", "pitch_ct"]


def load_recent_bullpen_usage(file_path="data/bullpen_usage.csv"):
    """
    Load recent bullpen usage data.

    Minimum expected columns:
    - team
    - date
    - relief_ip

    Optional reliever-level columns used for availability estimates:
    - pitcher_name / pitcher / reliever_name / reliever / player_name
    - pitch_count / pitches / pitch_ct

    If no file exists yet, return an empty dataframe with the minimum expected
    columns so downstream code can safely operate.
    """

    usage_path = Path(file_path)

    if not usage_path.exists():
        return pd.DataFrame(columns=["team", "date", "relief_ip"])

    usage_df = pd.read_csv(usage_path)

    for column in ["team", "date", "relief_ip"]:
        if column not in usage_df.columns:
            usage_df[column] = pd.Series(dtype="object")

    return usage_df.copy()


def _prepare_team_usage(team, game_log_df):
    """Filter and clean bullpen usage rows for one team."""
    if game_log_df.empty:
        return pd.DataFrame()

    team_games = game_log_df.loc[game_log_df["team"] == team].copy()
    if team_games.empty:
        return pd.DataFrame()

    team_games["date"] = pd.to_datetime(team_games["date"], errors="coerce")
    team_games["relief_ip"] = pd.to_numeric(team_games["relief_ip"], errors="coerce")
    team_games = team_games.dropna(subset=["date", "relief_ip"])
    if team_games.empty:
        return pd.DataFrame()

    return team_games


def _get_column_name(columns, candidates):
    """Return the first matching column name from a list of candidates."""
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _estimate_unavailable_key_relievers(team_games):
    """
    Estimate unavailable high-leverage relievers from recent pitch counts.

    A reliever is treated as unavailable if:
    - they threw more than 25 pitches yesterday, or
    - they threw more than 40 pitches across the last two days.

    To keep the penalty small and deterministic, only the top two unavailable
    relievers are counted. Those relievers are approximated as the team's key
    bullpen arms using the most recent pitch-count workload present in the data.
    """
    reliever_col = _get_column_name(team_games.columns, RELIEVER_NAME_CANDIDATES)
    pitch_count_col = _get_column_name(team_games.columns, PITCH_COUNT_CANDIDATES)
    if reliever_col is None or pitch_count_col is None:
        return 0

    reliever_usage = team_games.copy()
    reliever_usage[pitch_count_col] = pd.to_numeric(reliever_usage[pitch_count_col], errors="coerce")
    reliever_usage[reliever_col] = reliever_usage[reliever_col].astype(str).str.strip()
    reliever_usage = reliever_usage.dropna(subset=[pitch_count_col])
    reliever_usage = reliever_usage.loc[reliever_usage[reliever_col] != ""]
    if reliever_usage.empty:
        return 0

    latest_date = reliever_usage["date"].max()
    yesterday_cutoff = latest_date - pd.Timedelta(days=1)
    two_day_cutoff = latest_date - pd.Timedelta(days=2)

    yesterday_usage = reliever_usage.loc[reliever_usage["date"] >= yesterday_cutoff]
    two_day_usage = reliever_usage.loc[reliever_usage["date"] >= two_day_cutoff]

    yesterday_totals = (
        yesterday_usage.groupby(reliever_col, as_index=True)[pitch_count_col].sum()
        if not yesterday_usage.empty
        else pd.Series(dtype="float64")
    )
    two_day_totals = (
        two_day_usage.groupby(reliever_col, as_index=True)[pitch_count_col].sum()
        if not two_day_usage.empty
        else pd.Series(dtype="float64")
    )
    recent_workload = (
        two_day_usage.groupby(reliever_col, as_index=True)[pitch_count_col].sum()
        if not two_day_usage.empty
        else pd.Series(dtype="float64")
    )
    if recent_workload.empty:
        recent_workload = (
            reliever_usage.groupby(reliever_col, as_index=True)[pitch_count_col].sum()
            if not reliever_usage.empty
            else pd.Series(dtype="float64")
        )
    if recent_workload.empty:
        return 0

    unavailable_relievers = []
    for reliever_name in recent_workload.sort_values(ascending=False).index:
        pitches_yesterday = float(yesterday_totals.get(reliever_name, 0.0))
        pitches_last_two_days = float(two_day_totals.get(reliever_name, 0.0))
        if (
            pitches_yesterday > UNAVAILABLE_YESTERDAY_PITCHES
            or pitches_last_two_days > UNAVAILABLE_TWO_DAY_PITCHES
        ):
            unavailable_relievers.append(reliever_name)

    return min(len(unavailable_relievers), MAX_KEY_RELIEVERS_COUNTED)


def _estimate_bullpen_availability_penalty(team_games):
    """
    Convert unavailable key relievers into a small bullpen downgrade.

    Higher bullpen ratings in this project represent worse run prevention, so an
    unavailable key reliever adds a small positive penalty. The adjustment is
    intentionally capped so it complements rather than overwhelms the base
    bullpen rating and the broader fatigue estimate.
    """
    unavailable_count = _estimate_unavailable_key_relievers(team_games)
    return unavailable_count * UNAVAILABLE_RELIEVER_PENALTY


def estimate_bullpen_fatigue(team, game_log_df):
    """
    Estimate bullpen fatigue plus reliever availability adjustment.

    The base fatigue component uses total relief innings over the last 3 days.
    A small additional penalty is applied if key relievers are likely
    unavailable from recent high pitch counts.
    """

    team_games = _prepare_team_usage(team, game_log_df)
    if team_games.empty:
        return 0.00

    latest_date = team_games["date"].max()
    cutoff_date = latest_date - pd.Timedelta(days=2)

    recent_relief_ip = team_games.loc[team_games["date"] >= cutoff_date, "relief_ip"].sum()

    if recent_relief_ip <= 6:
        fatigue_penalty = 0.00
    elif recent_relief_ip <= 10:
        fatigue_penalty = 0.02
    elif recent_relief_ip <= 14:
        fatigue_penalty = 0.05
    else:
        fatigue_penalty = 0.08

    availability_penalty = _estimate_bullpen_availability_penalty(team_games)
    return round(fatigue_penalty + availability_penalty, 3)
