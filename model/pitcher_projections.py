from pathlib import Path

import pandas as pd
from pybaseball import pitching_stats

FALLBACK_THROWS_MAP = {
    "Brayan Bello": "R",
    "Gerrit Cole": "R",
    "Tyler Glasnow": "R",
    "Chris Sale": "L",
    "Justin Steele": "L",
    "Sonny Gray": "R",
}


def build_pitcher_ratings(current_season=2024, min_ip=30):
    """
    Build pitcher ratings using blended FIP across two seasons.

    blended_fip =
        70% current season FIP
        30% previous season FIP

    Rating scale:
    - 1.00 = league average
    - below 1.00 = better pitcher
    - above 1.00 = worse pitcher
    """

    previous_season = current_season - 1

    print("Loading pitcher stats...")

    current_df = pitching_stats(current_season)
    previous_df = pitching_stats(previous_season)

    current_df = current_df[["Name", "FIP", "IP"]].copy()
    previous_df = previous_df[["Name", "FIP", "IP"]].copy()

    current_df = current_df.rename(
        columns={
            "Name": "pitcher_name",
            "FIP": "current_fip",
            "IP": "current_ip",
        }
    )

    previous_df = previous_df.rename(
        columns={
            "Name": "pitcher_name",
            "FIP": "previous_fip",
            "IP": "previous_ip",
        }
    )

    merged_df = pd.merge(
        current_df,
        previous_df,
        on="pitcher_name",
        how="outer",
    )

    # Filter extremely small samples
    merged_df = merged_df.fillna(0)

    merged_df = merged_df[
        (merged_df["current_ip"] >= min_ip) | (merged_df["previous_ip"] >= min_ip)
    ]

    # Blend FIP values
    merged_df["blended_fip"] = (
        merged_df["current_fip"] * 0.70 + merged_df["previous_fip"] * 0.30
    )

    # If one season is missing, fall back to available FIP
    merged_df.loc[merged_df["current_fip"] == 0, "blended_fip"] = merged_df["previous_fip"]
    merged_df.loc[merged_df["previous_fip"] == 0, "blended_fip"] = merged_df["current_fip"]

    league_avg_fip = merged_df["blended_fip"].mean()

    merged_df["pitcher_rating"] = merged_df["blended_fip"] / league_avg_fip

    # Clamp extreme values
    merged_df["pitcher_rating"] = merged_df["pitcher_rating"].clip(0.60, 1.60)

    ratings_df = merged_df[
        ["pitcher_name", "pitcher_rating", "blended_fip"]
    ].copy()

    ratings_df = ratings_df.rename(columns={"blended_fip": "fip"})
    ratings_df["throws"] = ratings_df["pitcher_name"].map(FALLBACK_THROWS_MAP).fillna("")
    ratings_df = ratings_df[["pitcher_name", "pitcher_rating", "fip", "throws"]]

    ratings_df = ratings_df.sort_values("pitcher_rating").reset_index(drop=True)

    output_path = Path("data/pitcher_ratings.csv")

    ratings_df.to_csv(output_path, index=False)

    print("Pitcher ratings saved to data/pitcher_ratings.csv")

    return ratings_df


if __name__ == "__main__":
    build_pitcher_ratings()
