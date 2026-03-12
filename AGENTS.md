# AGENTS.md

This repository builds a beginner-friendly MLB probability prediction and betting comparison model.

The goal is to predict MLB game win probabilities and compare them to sportsbook implied probabilities.

IMPORTANT:
The model must be probability-first, not line-first.

## Project Philosophy

The model predicts probabilities.
Sportsbook odds are converted to implied probabilities.
Comparisons happen using probability.

Primary outputs:
- home_win_prob
- away_win_prob
- market_home_implied_prob_no_vig
- market_away_implied_prob_no_vig
- edge_home
- edge_away

Fair moneylines are optional helper values.

## Build Order

1. Project setup
2. Database setup
3. Data ingestion
4. Feature engineering
5. Model training
6. Prediction pipeline
7. Backtesting

## Database Tables

Create these tables:
- teams
- games
- starting_pitchers
- team_daily_stats
- pitcher_daily_stats
- odds_snapshots
- model_features
- predictions

## Predictions Table Fields

Must include:
- home_win_prob
- away_win_prob
- market_home_implied_prob_raw
- market_away_implied_prob_raw
- market_home_implied_prob_no_vig
- market_away_implied_prob_no_vig
- edge_home
- edge_away
- recommended_side
- recommended_bet

## Feature Engineering

Create one row per game in model_features.

Include:
- home_win_pct_last10
- away_win_pct_last10
- home_runs_per_game_last14
- away_runs_per_game_last14
- home_runs_allowed_last14
- away_runs_allowed_last14
- home_starter_era
- away_starter_era
- home_starter_fip
- away_starter_fip
- home_bullpen_ip_last3
- away_bullpen_ip_last3
- home_field_flag
- target_home_win

Prevent future data leakage.

## Modeling Rules

Use logistic regression first.
Predict home team win probability.
Save models into data/models/.

## Backtesting Rules

Compare model probabilities to no-vig market implied probabilities.
Only simulate bets when edge is at least 0.03.

## Coding Rules

Keep code simple, readable, and well commented.
Prefer:
- pandas
- numpy
- scikit-learn
- requests
- sqlite3

Avoid unnecessary complexity.