import pandas as pd
import pytest
import numpy as np

from app.models.predict_win_probability import (
    RECOMMENDED_BET_EDGE_THRESHOLD,
    build_market_comparison_lookup,
    build_prediction_rows,
)


class DummyModel:
    def predict_proba(self, feature_frame):
        return np.array([[0.42, 0.58] for _ in range(len(feature_frame))])


def test_build_market_comparison_lookup_averages_latest_book_probabilities():
    market_odds_df = pd.DataFrame(
        [
            {"game_id": 10, "sportsbook_name": "book_a", "home_moneyline": -120, "away_moneyline": 110},
            {"game_id": 10, "sportsbook_name": "book_b", "home_moneyline": -130, "away_moneyline": 120},
        ]
    )

    market_lookup = build_market_comparison_lookup(market_odds_df)

    assert 10 in market_lookup
    assert market_lookup[10]["market_home_implied_prob_raw"] > 0.5
    assert market_lookup[10]["market_away_implied_prob_raw"] < 0.5
    assert abs(
        market_lookup[10]["market_home_implied_prob_no_vig"]
        + market_lookup[10]["market_away_implied_prob_no_vig"]
        - 1.0
    ) < 1e-9


def test_build_prediction_rows_sets_market_edges_and_recommendation():
    prediction_frame = pd.DataFrame(
        [
            {
                "game_id": 25,
                "home_win_pct_last10": 0.7,
                "away_win_pct_last10": 0.4,
            }
        ]
    )
    market_lookup = {
        25: {
            "market_home_implied_prob_raw": 0.52,
            "market_away_implied_prob_raw": 0.50,
            "market_home_implied_prob_no_vig": 0.50,
            "market_away_implied_prob_no_vig": 0.50,
        }
    }

    prediction_rows = build_prediction_rows(
        prediction_frame=prediction_frame,
        model=DummyModel(),
        feature_columns=["home_win_pct_last10", "away_win_pct_last10"],
        market_lookup=market_lookup,
    )

    assert len(prediction_rows) == 1
    row = prediction_rows[0]
    assert row["home_win_prob"] == pytest.approx(0.58)
    assert row["away_win_prob"] == pytest.approx(0.42)
    assert row["edge_home"] == pytest.approx(0.08)
    assert row["edge_away"] == pytest.approx(-0.08)
    assert row["recommended_side"] == "home"
    assert row["recommended_bet"] == int(0.08 >= RECOMMENDED_BET_EDGE_THRESHOLD)
