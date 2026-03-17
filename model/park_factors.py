import pandas as pd


def load_park_factors(file_path="data/park_factors.csv"):
    return pd.read_csv(file_path)


def get_park_factor(home_team, park_df):
    team_row = park_df.loc[park_df["team"] == home_team]

    if team_row.empty:
        return 1.00

    return float(team_row.iloc[0]["park_factor"])
