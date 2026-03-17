def calculate_expected_runs(
    home_offense,
    away_offense,
    home_pitching,
    away_pitching,
    league_avg_runs=4.6,
    home_field_boost=1.04,
):
    """
    Estimate expected runs for each team from offense, opponent pitching,
    league scoring environment, and home-field advantage.
    """

    home_lambda = league_avg_runs * home_offense * away_pitching * home_field_boost
    away_lambda = league_avg_runs * away_offense * home_pitching

    return {
        "home_lambda": round(home_lambda, 3),
        "away_lambda": round(away_lambda, 3),
    }
