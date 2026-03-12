# MLB Betting Model

This project is a beginner-friendly MLB probability model.

The main goal is to estimate each team's chance to win a game, then compare those model probabilities to sportsbook implied probabilities.

This project is intentionally probability-first:

- predict `home_win_prob`
- predict `away_win_prob`
- convert sportsbook odds into implied probabilities
- compare model probability vs. market probability
- flag possible value with `edge_home` and `edge_away`

## Phase 1 Goal

Phase 1 sets up a clean project foundation.

This phase does not build the full model yet. It prepares the folders, starter files, and database schema we will use in later phases.

## Project Structure

```text
mlb-betting-model/
  app/
    api/          # future prediction pipeline helpers
    backtest/     # future betting simulation code
    db/           # database connection helpers
    features/     # feature engineering code
    ingest/       # data collection and loading code
    models/       # model training and prediction code
    utils/        # shared helpers
    config.py     # simple settings and paths
    main.py       # starter entry point
  data/
    models/       # saved trained models
    processed/    # cleaned datasets
    raw/          # raw downloaded data
  db/
    schema.sql    # starter SQLite schema
  tests/
    test_smoke.py # simple starter test
  .env.example
  requirements.txt
  README.md
```

## Beginner-Friendly Setup

1. Create a virtual environment.
2. Install the project requirements.
3. Copy `.env.example` to `.env`.
4. Run the starter app.

Example commands:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.main
```

## What Comes Next

The planned build order is:

1. Project setup
2. Database setup
3. Data ingestion
4. Feature engineering
5. Model training
6. Prediction pipeline
7. Backtesting

## Core Outputs

Later phases will produce these important prediction fields:

- `home_win_prob`
- `away_win_prob`
- `market_home_implied_prob_raw`
- `market_away_implied_prob_raw`
- `market_home_implied_prob_no_vig`
- `market_away_implied_prob_no_vig`
- `edge_home`
- `edge_away`
- `recommended_side`
- `recommended_bet`

## Notes

- Logistic regression is the first modeling approach.
- SQLite is the starter database.
- Models will be saved in `data/models/`.
- Code should stay simple, readable, and well commented.
