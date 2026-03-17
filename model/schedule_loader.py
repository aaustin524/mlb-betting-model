import pandas as pd


MATCHUP_COLUMNS = ["away_team", "home_team", "away_pitcher", "home_pitcher"]


def _load_local_matchups(file_path="data/matchups.csv"):
    matchups = pd.read_csv(file_path)

    for column in MATCHUP_COLUMNS:
        if column not in matchups.columns:
            matchups[column] = ""

    return matchups[MATCHUP_COLUMNS].copy()


def _load_live_matchups():
    """
    Placeholder for live daily schedule loading from the MLB Stats API.

    This function is structured so a live source can later provide today's
    away/home teams and probable starters without changing the app code.
    """

    raise NotImplementedError("Live schedule loading is not implemented yet.")


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
