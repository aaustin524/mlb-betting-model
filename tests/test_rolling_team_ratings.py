import sqlite3

import pandas as pd

from model.rolling_team_ratings import build_rolling_team_ratings


def test_build_rolling_team_ratings_preserves_shape_and_blends_recent_form(tmp_path):
    baseline_path = tmp_path / "teams.csv"
    db_path = tmp_path / "ratings.sqlite"

    baseline_df = pd.DataFrame(
        {
            "team": ["Atlanta Braves", "Miami Marlins"],
            "offense_vs_rhp": [1.00, 1.00],
            "offense_vs_lhp": [1.00, 1.00],
            "pitching": [1.00, 1.00],
            "bullpen": [1.00, 1.00],
        }
    )
    baseline_df.to_csv(baseline_path, index=False)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE games (
                game_id INTEGER PRIMARY KEY,
                game_date TEXT NOT NULL,
                home_team_id INTEGER NOT NULL,
                away_team_id INTEGER NOT NULL,
                home_score INTEGER,
                away_score INTEGER
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO games (game_id, game_date, home_team_id, away_team_id, home_score, away_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "2025-07-01", 144, 146, 8, 2),
                (2, "2025-07-02", 146, 144, 1, 7),
                (3, "2025-07-03", 144, 146, 6, 3),
                (4, "2025-07-04", 146, 144, 2, 5),
            ],
        )
        connection.commit()

    updated_df = build_rolling_team_ratings(
        baseline_path=baseline_path,
        db_path=db_path,
        baseline_weight=0.7,
        recent_weight=0.3,
        offense_lookback_games=4,
        bullpen_lookback_games=4,
    )

    assert list(updated_df.columns) == [
        "team",
        "offense_vs_rhp",
        "offense_vs_lhp",
        "pitching",
        "bullpen",
    ]
    assert set(updated_df["team"]) == {"Atlanta Braves", "Miami Marlins"}

    braves_row = updated_df.loc[updated_df["team"] == "Atlanta Braves"].iloc[0]
    marlins_row = updated_df.loc[updated_df["team"] == "Miami Marlins"].iloc[0]

    assert braves_row["offense_vs_rhp"] > 1.0
    assert braves_row["offense_vs_lhp"] > 1.0
    assert braves_row["bullpen"] < 1.0
    assert marlins_row["offense_vs_rhp"] < 1.0
    assert marlins_row["bullpen"] > 1.0
