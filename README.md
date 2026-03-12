# MLB Betting Model

This project is a beginner-friendly MLB probability model.

The main goal is to estimate each team's chance to win a game, then compare those model probabilities to sportsbook implied probabilities.

This project is intentionally probability-first:

- predict `home_win_prob`
- predict `away_win_prob`
- convert sportsbook odds into implied probabilities
- compare model probability vs. market probability
- flag possible value with `edge_home` and `edge_away`

## Phase 6 Goal

Phase 6 adds the first prediction pipeline.

This phase loads the trained home win model, scores `model_features`, and saves `home_win_prob` and `away_win_prob` into the `predictions` table.

## Project Structure

```text
mlb-betting-model/
  app/
    api/                             # future prediction pipeline helpers
    backtest/                        # future betting simulation code
    db/                              # database connection helpers
    features/                        # feature engineering code
      build_game_features.py         # builds game-level features from past games
    ingest/                          # data collection and loading code
      historical_games.py            # loads historical MLB games from the Stats API
    models/                          # model training and prediction code
      train_win_probability.py       # trains the logistic regression home win model
      predict_win_probability.py     # scores games and saves win probabilities
    utils/                           # shared helpers
    config.py                        # simple settings and paths
    main.py                          # starter command-line entry point
  data/
    models/                          # saved trained models
    processed/                       # cleaned datasets
    raw/                             # raw downloaded data
  db/
    schema.sql                       # SQLite schema used to create the database
  tests/
    test_smoke.py                    # simple starter test
  .env.example
  requirements.txt
  README.md
```

## Beginner-Friendly Setup

1. Create a virtual environment.
2. Install the project requirements.
3. Copy `.env.example` to `.env`.
4. Initialize the database.
5. Load historical games.
6. Build game features.
7. Train the win probability model.
8. Generate predictions.

Example commands:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.main init-db
python -m app.ingest.historical_games --start-date 2024-03-28 --end-date 2024-09-30
python -m app.features.build_game_features
python -m app.models.train_win_probability
python -m app.models.predict_win_probability
```

## Historical Game Ingestion

The historical game loader uses the MLB Stats API as the data source.

Run it like this:

```powershell
python -m app.ingest.historical_games --start-date 2024-03-28 --end-date 2024-09-30
```

Helpful options:

- `--chunk-days 30` splits large requests into smaller date ranges.
- `--log-level DEBUG` prints more detailed logs while the script runs.

What the script does:

- fetches real MLB schedule data from the Stats API
- keeps only completed games
- normalizes fields into the `games` table shape
- upserts team rows first so foreign keys stay valid
- upserts probable pitcher rows when the API provides them
- upserts game rows by `game_id` to prevent duplicates on reruns

## Game Feature Building

The feature builder reads completed games from the `games` table and writes one row per game into `model_features`.

Run it like this:

```powershell
python -m app.features.build_game_features
```

Helpful options:

- `--start-date 2024-06-01` only writes features for games on or after that date.
- `--end-date 2024-09-30` only writes features for games on or before that date.
- `--log-level DEBUG` prints more detailed logs while the script runs.

The script prevents future data leakage by using only games with a date earlier than the current game's date when it calculates rolling features.

Phase 4 currently builds these fields:

- `home_win_pct_last10`
- `away_win_pct_last10`
- `home_runs_per_game_last14`
- `away_runs_per_game_last14`
- `home_runs_allowed_last14`
- `away_runs_allowed_last14`
- `home_field_flag`
- `target_home_win`

## Model Training

The training script loads `model_features` into a pandas DataFrame, trains a logistic regression model with an 80/20 train/test split, prints evaluation metrics, and saves the model artifact.

Run it like this:

```powershell
python -m app.models.train_win_probability
```

The script prints:

- `accuracy`
- `log loss`
- `ROC AUC`

The trained model is saved to:

- `data/models/home_win_model.pkl`

## Prediction Pipeline

The prediction script loads the trained model, reads rows from `model_features`, uses the same v1 feature columns as training, and saves probabilities into `predictions`.

Run it like this:

```powershell
python -m app.models.predict_win_probability
```

Each saved prediction includes:

- `game_id`
- `model_version`
- `prediction_time`
- `home_win_prob`
- `away_win_prob`

The script replaces older rows for the same `game_id` and `model_version` so reruns stay clean.

## Database Initialization

To create the SQLite database and all Phase 2 tables, run:

```powershell
python -m app.main init-db
```

This creates the database file at `db/mlb_betting_model.sqlite`.

The initialization command creates these tables:

- `teams`
- `games`
- `starting_pitchers`
- `team_daily_stats`
- `pitcher_daily_stats`
- `odds_snapshots`
- `model_features`
- `predictions`

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
