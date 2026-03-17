import pandas as pd


def load_hitter_ratings(file_path="data/hitter_ratings.csv"):
    hitter_ratings_df = pd.read_csv(file_path)

    if "player_name" not in hitter_ratings_df.columns:
        hitter_ratings_df["player_name"] = ""

    if "hitter_rating" not in hitter_ratings_df.columns:
        hitter_ratings_df["hitter_rating"] = 1.00

    return hitter_ratings_df[["player_name", "hitter_rating"]].copy()


def load_projected_lineups(file_path="data/projected_lineups.csv"):
    projected_lineups_df = pd.read_csv(file_path)

    if "team" not in projected_lineups_df.columns:
        projected_lineups_df["team"] = ""

    if "player_name" not in projected_lineups_df.columns:
        projected_lineups_df["player_name"] = ""

    return projected_lineups_df[["team", "player_name"]].copy()


def calculate_lineup_adjustment(team, hitter_ratings_df, projected_lineups_df):
    """
    Build a simple lineup multiplier from the projected 9 hitters.

    If lineup data is missing, fall back to 1.00.
    """

    if hitter_ratings_df.empty or projected_lineups_df.empty:
        return 1.00

    team_lineup = projected_lineups_df.loc[projected_lineups_df["team"] == team].copy()

    if team_lineup.empty:
        return 1.00

    # Use the projected nine hitters for the team when available.
    team_lineup = team_lineup.head(9)

    merged_df = team_lineup.merge(
        hitter_ratings_df,
        on="player_name",
        how="left",
    )

    if merged_df["hitter_rating"].dropna().empty:
        return 1.00

    average_hitter_rating = merged_df["hitter_rating"].dropna().mean()

    # Hitter ratings are already centered around 1.00, so the lineup
    # multiplier can use the team average directly.
    return round(float(average_hitter_rating), 3)
