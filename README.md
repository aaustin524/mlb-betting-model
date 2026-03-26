# MLB Betting Model

This project is a beginner-friendly MLB probability model.

The main goal is to estimate each team's chance to win a game, then compare those model probabilities to sportsbook implied probabilities.

This project is intentionally probability-first:

- predict `home_win_prob`
- predict `away_win_prob`
- convert sportsbook odds into implied probabilities
- compare model probability vs. market probability
- flag possible value with `edge_home` and `edge_away`

## Reflex Cloud Deployment

The Reflex app can be deployed on Reflex Cloud.

Deployment checklist, required environment variables, and smoke-test steps live in:

- [`DEPLOY.md`](/Users/aaustin2/mlb-betting-model/DEPLOY.md)

## Odds Ingestion

The first odds ingestion step loads MLB moneyline odds into the `odds_snapshots` table.

It stores these fields:

- `game_id`
- `sportsbook_name`
- `snapshot_time`
- `home_moneyline`
- `away_moneyline`

This version uses The Odds API MLB moneyline feed and matches the odds back to games already stored in the database.

Before running it, set your API key in the environment:

```powershell
$env:ODDS_API_KEY="your_api_key_here"
```

Run the odds feed like this:

```powershell
python -m app.ingest.odds_feed --start-date 2026-03-12 --end-date 2026-03-12
```

Helpful options:

- `--regions us` uses U.S. sportsbooks.
- `--log-level DEBUG` prints more detailed logs.

The script logs:

- how many odds records were fetched
- how many rows were inserted
- how many rows were skipped

Duplicate rows are avoided by a unique index on `game_id`, `sportsbook_name`, and `snapshot_time`.

## Probability Helpers

The shared probability helpers live in `app/utils/probabilities.py`.

They include:

- `american_to_implied_prob`
- `no_vig_probs`

These helpers convert American odds into implied probabilities and remove vig by normalizing the two sides.

## Phase 6 Goal

Phase 6 adds the first prediction pipeline.

This phase loads the trained home win model, scores `model_features`, and saves `home_win_prob` and `away_win_prob` into the `predictions` table.

The saved prediction rows now also store the market comparison fields required for the project:

- `market_home_implied_prob_raw`
- `market_away_implied_prob_raw`
- `market_home_implied_prob_no_vig`
- `market_away_implied_prob_no_vig`
- `edge_home`
- `edge_away`
- `recommended_side`
- `recommended_bet`

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
      odds_feed.py                   # loads MLB moneyline odds into odds_snapshots
    models/                          # model training and prediction code
      train_win_probability.py       # trains the logistic regression home win model
      predict_win_probability.py     # scores games and saves win probabilities
    utils/                           # shared helpers
      probabilities.py               # implied probability and no-vig helpers
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
6. Load moneyline odds.
7. Build game features.
8. Train the win probability model.
9. Generate predictions.

Example commands:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
$env:ODDS_API_KEY="your_api_key_here"
python -m app.main init-db
python -m app.ingest.historical_games --start-date 2024-03-28 --end-date 2024-09-30
python -m app.ingest.odds_feed --start-date 2024-03-28 --end-date 2024-09-30
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

The prediction script loads the trained model, reads rows from `model_features`, uses the same saved feature columns as training, and saves probabilities into `predictions`.

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
- `market_home_implied_prob_raw`
- `market_away_implied_prob_raw`
- `market_home_implied_prob_no_vig`
- `market_away_implied_prob_no_vig`
- `edge_home`
- `edge_away`
- `recommended_side`
- `recommended_bet`

The script replaces older rows for the same `game_id` and `model_version` so reruns stay clean.

Market comparison fields are built from the latest available odds snapshot for each sportsbook, then averaged into a simple consensus by game.

## Backtesting

The repo now includes a simple probability-first backtest module:

```powershell
python -m app.backtest.run_backtest
```

Backtest rules:

- compare model probabilities to no-vig market implied probabilities
- only place a simulated bet when the selected side has `edge >= 0.03`
- use a flat 1-unit stake per qualifying bet

## Render Deployment

If you want a shareable URL without managing your own server, Render is a good fit for this project.

This repo now includes:

- [`render.yaml`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/render.yaml) for a Render web service
- [`.streamlit/config.toml`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/.streamlit/config.toml) for headless production startup
- [`.streamlit/secrets.toml.example`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/.streamlit/secrets.toml.example) as a local secrets template
- environment-variable support for:
  - `MLB_MODEL_DB_PATH`
  - `MLB_MODEL_HISTORY_DIR`

Recommended Render setup:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint or Web Service from the repo.
3. Attach a persistent disk mounted at `/var/data`.
4. Set these environment variables in Render:
   - `ODDS_API_KEY`
   - `MLB_MODEL_DB_PATH=/var/data/mlb_betting_model.sqlite`
   - `MLB_MODEL_HISTORY_DIR=/var/data/history`
5. Deploy the service.

The Streamlit start command used by Render is:

```bash
streamlit run app/app.py --server.address 0.0.0.0 --server.port $PORT
```

Notes:

- SQLite and snapshot history need persistent disk. Do not use an ephemeral filesystem for production data.
- The local file [`.streamlit/secrets.toml`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/.streamlit/secrets.toml) should not be relied on in Render. Use Render environment variables instead.
- For local development, copy [`.streamlit/secrets.toml.example`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/.streamlit/secrets.toml.example) to [`.streamlit/secrets.toml`](/Users/aaust/OneDrive/Documents/GitHub/mlb-betting-model/.streamlit/secrets.toml) and add your key there.
- If the current `ODDS_API_KEY` in local secrets was ever committed or shared, rotate it before deploying.

## Reflex Front End

The repo now includes a separate Reflex app that lives alongside the existing Streamlit app.

The Streamlit app is still the current entrypoint:

```bash
streamlit run app/app.py
```

The new Reflex app is isolated under `reflex_app/` and reuses the existing model and service modules instead of replacing them.

Install Reflex locally:

```bash
pip install -r requirements.txt
```

Run the Reflex app from the repo root:

```bash
reflex run
```

Useful first-run notes:

- Reflex reads [`rxconfig.py`](/Users/aaustin2/mlb-betting-model/rxconfig.py) at the project root.
- The main Reflex app object lives in [`reflex_app/reflex_app.py`](/Users/aaustin2/mlb-betting-model/reflex_app/reflex_app.py).
- The current local database at [`db/mlb_betting_model.sqlite`](/Users/aaustin2/mlb-betting-model/db/mlb_betting_model.sqlite) may be empty, so the Reflex board falls back to the CSV matchup inputs when odds or prediction rows are missing.

Files added for the Reflex UI:

- [`rxconfig.py`](/Users/aaustin2/mlb-betting-model/rxconfig.py)
- [`reflex_app/reflex_app.py`](/Users/aaustin2/mlb-betting-model/reflex_app/reflex_app.py)
- [`reflex_app/styles.py`](/Users/aaustin2/mlb-betting-model/reflex_app/styles.py)
- [`reflex_app/pages/dashboard.py`](/Users/aaustin2/mlb-betting-model/reflex_app/pages/dashboard.py)
- [`reflex_app/pages/daily_matchups.py`](/Users/aaustin2/mlb-betting-model/reflex_app/pages/daily_matchups.py)
- [`reflex_app/pages/drivers.py`](/Users/aaustin2/mlb-betting-model/reflex_app/pages/drivers.py)
- [`reflex_app/pages/projections.py`](/Users/aaustin2/mlb-betting-model/reflex_app/pages/projections.py)
- [`reflex_app/pages/settings.py`](/Users/aaustin2/mlb-betting-model/reflex_app/pages/settings.py)
- [`reflex_app/components/header.py`](/Users/aaustin2/mlb-betting-model/reflex_app/components/header.py)
- [`reflex_app/components/cards.py`](/Users/aaustin2/mlb-betting-model/reflex_app/components/cards.py)
- [`reflex_app/components/filters.py`](/Users/aaustin2/mlb-betting-model/reflex_app/components/filters.py)
- [`reflex_app/components/tables.py`](/Users/aaustin2/mlb-betting-model/reflex_app/components/tables.py)
- [`reflex_app/components/shell.py`](/Users/aaustin2/mlb-betting-model/reflex_app/components/shell.py)
- [`reflex_app/services/legacy_adapter.py`](/Users/aaustin2/mlb-betting-model/reflex_app/services/legacy_adapter.py)
- [`reflex_app/services/app_data.py`](/Users/aaustin2/mlb-betting-model/reflex_app/services/app_data.py)
- [`reflex_app/state/app_state.py`](/Users/aaustin2/mlb-betting-model/reflex_app/state/app_state.py)

Existing files reused by the Reflex app:

- [`app/app.py`](/Users/aaustin2/mlb-betting-model/app/app.py) as the reference implementation for board calculations and thresholds
- [`model/game_engine.py`](/Users/aaustin2/mlb-betting-model/model/game_engine.py) for matchup simulation
- [`model/simulate_games.py`](/Users/aaustin2/mlb-betting-model/model/simulate_games.py) for win-probability simulation
- [`model/schedule_loader.py`](/Users/aaustin2/mlb-betting-model/model/schedule_loader.py) for daily matchups
- [`model/team_loader.py`](/Users/aaustin2/mlb-betting-model/model/team_loader.py) for team ratings
- [`model/lineup_strength.py`](/Users/aaustin2/mlb-betting-model/model/lineup_strength.py) for lineup adjustments
- [`app/utils/season_monitor.py`](/Users/aaustin2/mlb-betting-model/app/utils/season_monitor.py) for standings, drivers, and projections
- [`app/utils/probabilities.py`](/Users/aaustin2/mlb-betting-model/app/utils/probabilities.py) for implied probability and no-vig math
- [`app/db/connection.py`](/Users/aaustin2/mlb-betting-model/app/db/connection.py) for SQLite access

Requirements updated:

- [`requirements.txt`](/Users/aaustin2/mlb-betting-model/requirements.txt) now includes `reflex`
