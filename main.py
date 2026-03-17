from model.team_loader import load_team_ratings
from model.run_expectancy import calculate_expected_runs
from model.simulate_games import simulate_game

teams = load_team_ratings()

home_team = "Yankees"
away_team = "Red Sox"

home_offense = teams.loc[home_team, "offense"]
home_pitching = teams.loc[home_team, "pitching"]

away_offense = teams.loc[away_team, "offense"]
away_pitching = teams.loc[away_team, "pitching"]

expected = calculate_expected_runs(
    home_offense=home_offense,
    away_offense=away_offense,
    home_pitching=home_pitching,
    away_pitching=away_pitching
)

result = simulate_game(
    lambda_home=expected["home_lambda"],
    lambda_away=expected["away_lambda"],
    sims=10000
)

home_win_prob = result["home_win_prob"]
away_win_prob = result["away_win_prob"] + result["tie_prob"]

print()
print(f"Matchup: {away_team} at {home_team}")
print(f"Expected Score: {home_team} {expected['home_lambda']:.1f}, {away_team} {expected['away_lambda']:.1f}")
print("Win Probabilities:")
print(f"- {home_team}: {home_win_prob:.1%}")
print(f"- {away_team}: {away_win_prob:.1%}")
print()