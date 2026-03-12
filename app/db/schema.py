"""SQLite schema helpers for the MLB betting model project."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DB_PATH


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS teams (
    team_id INTEGER PRIMARY KEY,
    team_name TEXT NOT NULL,
    team_abbr TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY,
    game_date TEXT NOT NULL,
    season INTEGER NOT NULL,
    status TEXT,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    home_starting_pitcher_id INTEGER,
    away_starting_pitcher_id INTEGER,
    FOREIGN KEY (home_team_id) REFERENCES teams (team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams (team_id),
    FOREIGN KEY (home_starting_pitcher_id) REFERENCES starting_pitchers (pitcher_id),
    FOREIGN KEY (away_starting_pitcher_id) REFERENCES starting_pitchers (pitcher_id)
);

CREATE TABLE IF NOT EXISTS starting_pitchers (
    pitcher_id INTEGER PRIMARY KEY,
    pitcher_name TEXT NOT NULL,
    team_id INTEGER,
    throws_hand TEXT,
    FOREIGN KEY (team_id) REFERENCES teams (team_id)
);

CREATE TABLE IF NOT EXISTS team_daily_stats (
    stat_id INTEGER PRIMARY KEY,
    team_id INTEGER NOT NULL,
    game_date TEXT NOT NULL,
    wins INTEGER,
    losses INTEGER,
    runs_scored REAL,
    runs_allowed REAL,
    FOREIGN KEY (team_id) REFERENCES teams (team_id)
);

CREATE TABLE IF NOT EXISTS pitcher_daily_stats (
    stat_id INTEGER PRIMARY KEY,
    pitcher_id INTEGER NOT NULL,
    game_date TEXT NOT NULL,
    innings_pitched REAL,
    earned_runs INTEGER,
    strikeouts INTEGER,
    walks INTEGER,
    fip REAL,
    FOREIGN KEY (pitcher_id) REFERENCES starting_pitchers (pitcher_id)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    sportsbook_name TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    home_moneyline INTEGER,
    away_moneyline INTEGER,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);

CREATE TABLE IF NOT EXISTS model_features (
    feature_id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL UNIQUE,
    home_win_pct_last10 REAL,
    away_win_pct_last10 REAL,
    home_runs_per_game_last14 REAL,
    away_runs_per_game_last14 REAL,
    home_runs_allowed_last14 REAL,
    away_runs_allowed_last14 REAL,
    home_starter_era REAL,
    away_starter_era REAL,
    home_starter_fip REAL,
    away_starter_fip REAL,
    home_bullpen_ip_last3 REAL,
    away_bullpen_ip_last3 REAL,
    home_field_flag INTEGER NOT NULL DEFAULT 1,
    target_home_win INTEGER,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL,
    model_version TEXT NOT NULL,
    prediction_time TEXT NOT NULL,
    home_win_prob REAL NOT NULL,
    away_win_prob REAL NOT NULL,
    market_home_implied_prob_raw REAL,
    market_away_implied_prob_raw REAL,
    market_home_implied_prob_no_vig REAL,
    market_away_implied_prob_no_vig REAL,
    edge_home REAL,
    edge_away REAL,
    recommended_side TEXT,
    recommended_bet INTEGER,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);
"""


def get_db_path() -> Path:
    """Return the database path used by the project."""
    return DB_PATH


def initialize_database(db_path: Path | None = None) -> Path:
    """Create the SQLite database and all Phase 2 tables."""
    target_path = db_path or get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(SCHEMA_SQL)
        connection.commit()

    return target_path
