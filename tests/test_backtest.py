import pandas as pd
import pytest

from app.backtest.run_backtest import (
    EDGE_THRESHOLD,
    choose_bet_side,
    simulate_backtest_results,
    summarize_backtest_results,
)


def test_choose_bet_side_uses_minimum_edge_threshold():
    assert choose_bet_side(pd.Series({"edge_home": 0.02, "edge_away": 0.01})) is None
    assert choose_bet_side(pd.Series({"edge_home": EDGE_THRESHOLD, "edge_away": 0.01})) == "home"
    assert choose_bet_side(pd.Series({"edge_home": 0.04, "edge_away": 0.05})) == "away"


def test_simulate_backtest_results_places_only_qualified_bets():
    predictions_df = pd.DataFrame(
        [
            {
                "game_id": 1,
                "edge_home": 0.05,
                "edge_away": -0.05,
                "market_home_implied_prob_raw": 0.45,
                "market_away_implied_prob_raw": 0.60,
                "home_score": 5,
                "away_score": 3,
            },
            {
                "game_id": 2,
                "edge_home": 0.01,
                "edge_away": 0.02,
                "market_home_implied_prob_raw": 0.55,
                "market_away_implied_prob_raw": 0.47,
                "home_score": 2,
                "away_score": 6,
            },
        ]
    )

    results_df = simulate_backtest_results(predictions_df)

    assert list(results_df["game_id"]) == [1]
    assert results_df.iloc[0]["selected_side"] == "home"
    assert bool(results_df.iloc[0]["bet_won"]) is True
    assert results_df.iloc[0]["units"] > 1.2


def test_summarize_backtest_results_returns_basic_metrics():
    results_df = pd.DataFrame(
        [
            {"bet_won": True, "units": 1.1},
            {"bet_won": False, "units": -1.0},
        ]
    )

    summary = summarize_backtest_results(results_df)

    assert summary["bets"] == 2.0
    assert summary["wins"] == 1.0
    assert summary["losses"] == 1.0
    assert summary["win_rate"] == 0.5
    assert summary["units"] == pytest.approx(0.1)
    assert summary["roi"] == pytest.approx(0.05)
