import pandas as pd

from model.game_engine import simulate_matchup


def _build_team_frame():
    return pd.DataFrame(
        {
            "team": ["Away Team", "Home Team"],
            "offense_vs_rhp": [1.02, 1.05],
            "offense_vs_lhp": [1.01, 1.04],
            "bullpen": [1.00, 0.98],
        }
    ).set_index("team")


def test_simulate_matchup_returns_expected_keys():
    teams = _build_team_frame()

    result = simulate_matchup(home_team="Home Team", away_team="Away Team", teams=teams, sims=1000)

    expected_keys = {
        "away_team",
        "home_team",
        "away_lambda",
        "home_lambda",
        "away_win_prob",
        "home_win_prob",
        "adjusted_away_offense",
        "adjusted_home_offense",
        "adjusted_away_pitching",
        "adjusted_home_pitching",
        "away_bullpen_rating",
        "home_bullpen_rating",
        "park_factor",
        "weather_multiplier",
        "run_environment_factor",
        "run_dispersion",
    }

    assert expected_keys.issubset(result.keys())


def test_simulate_matchup_probabilities_are_valid():
    teams = _build_team_frame()

    result = simulate_matchup(home_team="Home Team", away_team="Away Team", teams=teams, sims=2000)

    assert 0 <= result["home_win_prob"] <= 1
    assert 0 <= result["away_win_prob"] <= 1
    assert abs((result["home_win_prob"] + result["away_win_prob"]) - 1.0) < 0.02


def test_simulate_matchup_expected_runs_are_positive():
    teams = _build_team_frame()

    result = simulate_matchup(home_team="Home Team", away_team="Away Team", teams=teams, sims=1000)

    assert result["home_lambda"] > 0
    assert result["away_lambda"] > 0
