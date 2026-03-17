import pandas as pd


def load_team_ratings(file_path="data/teams.csv"):
    df = pd.read_csv(file_path)

    # Keep a simple fallback if an older teams file still has one offense column.
    if "offense" in df.columns:
        df["offense_vs_rhp"] = df["offense"]
        df["offense_vs_lhp"] = df["offense"]

    # The app and simulation engine only require the rating columns below, so the
    # loader stays compatible even if the CSV later carries extra metadata.
    required_columns = ["team", "offense_vs_rhp", "offense_vs_lhp", "pitching", "bullpen"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"teams file is missing required columns: {missing_columns}")

    df = df[required_columns].set_index("team")
    return df
