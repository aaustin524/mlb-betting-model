"""SQLite schema helpers for the MLB betting model project."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from project_config import DB_PATH


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
    total_line REAL,
    over_price INTEGER,
    under_price INTEGER,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshots_unique
ON odds_snapshots (game_id, sportsbook_name, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game_time
ON odds_snapshots (game_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game_book_time
ON odds_snapshots (game_id, sportsbook_name, snapshot_time);

CREATE TABLE IF NOT EXISTS odds_api_cache (
    cache_id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL,
    sport_key TEXT NOT NULL,
    regions TEXT NOT NULL,
    markets TEXT NOT NULL,
    odds_format TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_team TEXT NOT NULL,
    commence_time TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    market_data_json TEXT NOT NULL,
    requests_remaining INTEGER,
    requests_used INTEGER,
    requests_last INTEGER,
    source TEXT NOT NULL DEFAULT 'LIVE API'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_api_cache_unique
ON odds_api_cache (event_id, regions, markets, odds_format);

CREATE INDEX IF NOT EXISTS idx_odds_api_cache_lookup
ON odds_api_cache (sport_key, regions, markets, odds_format, commence_time);

CREATE TABLE IF NOT EXISTS performance_bets (
    performance_bet_id INTEGER PRIMARY KEY,
    tracking_key TEXT NOT NULL UNIQUE,
    snapshot_group_id TEXT NOT NULL,
    snapshot_timestamp TEXT NOT NULL,
    snapshot_note TEXT,
    game_date TEXT,
    game_id INTEGER,
    game_match_method TEXT,
    away_team TEXT NOT NULL,
    home_team TEXT NOT NULL,
    market_type TEXT NOT NULL,
    event_id TEXT,
    bookmaker_key TEXT,
    sport_key TEXT,
    commence_time TEXT,
    sportsbook TEXT,
    pick TEXT NOT NULL,
    model_win_probability REAL,
    projected_total REAL,
    locked_line REAL,
    locked_odds INTEGER,
    locked_implied_probability REAL,
    market_implied_probability REAL,
    market_no_vig_probability REAL,
    edge REAL,
    ev REAL,
    best_bet_flag TEXT,
    signal_strength TEXT,
    is_actionable INTEGER NOT NULL DEFAULT 0,
    tracking_mode TEXT NOT NULL DEFAULT 'full_visible_board',
    edge_bucket TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    closing_line REAL,
    closing_odds INTEGER,
    closing_implied_probability REAL,
    closing_captured_at TEXT,
    clv_value REAL,
    clv_direction TEXT,
    close_status TEXT,
    result TEXT,
    units REAL,
    clv REAL,
    final_away_runs REAL,
    final_home_runs REAL,
    graded_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);

CREATE INDEX IF NOT EXISTS idx_performance_bets_game_date
ON performance_bets (game_date, snapshot_timestamp);

CREATE INDEX IF NOT EXISTS idx_performance_bets_market_type
ON performance_bets (market_type, signal_strength);

CREATE TABLE IF NOT EXISTS model_features (
    feature_id INTEGER PRIMARY KEY,
    game_id INTEGER NOT NULL UNIQUE,
    home_win_pct_last10 REAL,
    away_win_pct_last10 REAL,
    home_runs_per_game_last14 REAL,
    away_runs_per_game_last14 REAL,
    home_runs_allowed_last14 REAL,
    away_runs_allowed_last14 REAL,
    home_run_diff_last14 REAL,
    away_run_diff_last14 REAL,
    run_diff_edge_last14 REAL,
    home_starter_era REAL,
    away_starter_era REAL,
    home_starter_fip REAL,
    away_starter_fip REAL,
    starter_fip_edge REAL,
    home_bullpen_ip_last3 REAL,
    away_bullpen_ip_last3 REAL,
    bullpen_rest_edge REAL,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_game_model
ON predictions (game_id, model_version);

CREATE TABLE IF NOT EXISTS tracked_bets (
    tracking_id INTEGER PRIMARY KEY,
    tracking_key TEXT NOT NULL UNIQUE,
    grading_key TEXT,
    game_id INTEGER,
    game_match_method TEXT,
    snapshot_timestamp TEXT NOT NULL,
    snapshot_date TEXT,
    snapshot_type TEXT,
    data_mode TEXT,
    run_dispersion REAL,
    away_team TEXT NOT NULL,
    home_team TEXT NOT NULL,
    sportsbook TEXT,
    best_bet TEXT,
    bet_flag TEXT,
    best_total_bet TEXT,
    total_bet_flag TEXT,
    away_moneyline INTEGER,
    home_moneyline INTEGER,
    total_line REAL,
    over_price INTEGER,
    under_price INTEGER,
    open_home_ml INTEGER,
    open_away_ml INTEGER,
    open_total REAL,
    open_over_price INTEGER,
    open_under_price INTEGER,
    close_home_ml INTEGER,
    close_away_ml INTEGER,
    close_total REAL,
    close_over_price INTEGER,
    close_under_price INTEGER,
    clv_side REAL,
    clv_total REAL,
    clv_side_line_diff REAL,
    clv_total_line_diff REAL,
    market_timestamp_open TEXT,
    market_timestamp_close TEXT,
    final_away_runs REAL,
    final_home_runs REAL,
    side_pick_outcome TEXT,
    total_pick_outcome TEXT,
    side_units REAL,
    total_units REAL,
    grading_status TEXT DEFAULT 'ungraded',
    grading_source TEXT,
    graded_timestamp TEXT,
    grading_note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games (game_id)
);
"""

MODEL_FEATURE_COLUMNS = {
    "home_win_pct_last10": "REAL",
    "away_win_pct_last10": "REAL",
    "home_runs_per_game_last14": "REAL",
    "away_runs_per_game_last14": "REAL",
    "home_runs_allowed_last14": "REAL",
    "away_runs_allowed_last14": "REAL",
    "home_run_diff_last14": "REAL",
    "away_run_diff_last14": "REAL",
    "run_diff_edge_last14": "REAL",
    "home_starter_era": "REAL",
    "away_starter_era": "REAL",
    "home_starter_fip": "REAL",
    "away_starter_fip": "REAL",
    "starter_fip_edge": "REAL",
    "home_bullpen_ip_last3": "REAL",
    "away_bullpen_ip_last3": "REAL",
    "bullpen_rest_edge": "REAL",
    "home_field_flag": "INTEGER NOT NULL DEFAULT 1",
    "target_home_win": "INTEGER",
}

ODDS_SNAPSHOTS_COLUMNS = {
    "game_id": "INTEGER NOT NULL",
    "sportsbook_name": "TEXT NOT NULL",
    "snapshot_time": "TEXT NOT NULL",
    "home_moneyline": "INTEGER",
    "away_moneyline": "INTEGER",
    "total_line": "REAL",
    "over_price": "INTEGER",
    "under_price": "INTEGER",
}

PREDICTIONS_COLUMNS = {
    "game_id": "INTEGER NOT NULL",
    "model_version": "TEXT NOT NULL",
    "prediction_time": "TEXT NOT NULL",
    "home_win_prob": "REAL NOT NULL",
    "away_win_prob": "REAL NOT NULL",
    "market_home_implied_prob_raw": "REAL",
    "market_away_implied_prob_raw": "REAL",
    "market_home_implied_prob_no_vig": "REAL",
    "market_away_implied_prob_no_vig": "REAL",
    "edge_home": "REAL",
    "edge_away": "REAL",
    "recommended_side": "TEXT",
    "recommended_bet": "INTEGER",
}

TRACKED_BETS_COLUMNS = {
    "tracking_key": "TEXT",
    "grading_key": "TEXT",
    "game_id": "INTEGER",
    "game_match_method": "TEXT",
    "snapshot_timestamp": "TEXT",
    "snapshot_date": "TEXT",
    "snapshot_type": "TEXT",
    "data_mode": "TEXT",
    "run_dispersion": "REAL",
    "away_team": "TEXT",
    "home_team": "TEXT",
    "sportsbook": "TEXT",
    "best_bet": "TEXT",
    "bet_flag": "TEXT",
    "best_total_bet": "TEXT",
    "total_bet_flag": "TEXT",
    "away_moneyline": "INTEGER",
    "home_moneyline": "INTEGER",
    "total_line": "REAL",
    "over_price": "INTEGER",
    "under_price": "INTEGER",
    "open_home_ml": "INTEGER",
    "open_away_ml": "INTEGER",
    "open_total": "REAL",
    "open_over_price": "INTEGER",
    "open_under_price": "INTEGER",
    "close_home_ml": "INTEGER",
    "close_away_ml": "INTEGER",
    "close_total": "REAL",
    "close_over_price": "INTEGER",
    "close_under_price": "INTEGER",
    "clv_side": "REAL",
    "clv_total": "REAL",
    "clv_side_line_diff": "REAL",
    "clv_total_line_diff": "REAL",
    "market_timestamp_open": "TEXT",
    "market_timestamp_close": "TEXT",
    "final_away_runs": "REAL",
    "final_home_runs": "REAL",
    "side_pick_outcome": "TEXT",
    "total_pick_outcome": "TEXT",
    "side_units": "REAL",
    "total_units": "REAL",
    "grading_status": "TEXT DEFAULT 'ungraded'",
    "grading_source": "TEXT",
    "graded_timestamp": "TEXT",
    "grading_note": "TEXT",
    "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
}

ODDS_API_CACHE_COLUMNS = {
    "event_id": "TEXT NOT NULL",
    "sport_key": "TEXT NOT NULL",
    "regions": "TEXT NOT NULL",
    "markets": "TEXT NOT NULL",
    "odds_format": "TEXT NOT NULL",
    "away_team": "TEXT NOT NULL",
    "home_team": "TEXT NOT NULL",
    "commence_time": "TEXT NOT NULL",
    "fetched_at": "TEXT NOT NULL",
    "market_data_json": "TEXT NOT NULL",
    "requests_remaining": "INTEGER",
    "requests_used": "INTEGER",
    "requests_last": "INTEGER",
    "source": "TEXT NOT NULL DEFAULT 'LIVE API'",
}

PERFORMANCE_BETS_COLUMNS = {
    "tracking_key": "TEXT NOT NULL",
    "snapshot_group_id": "TEXT NOT NULL",
    "snapshot_timestamp": "TEXT NOT NULL",
    "snapshot_note": "TEXT",
    "game_date": "TEXT",
    "game_id": "INTEGER",
    "game_match_method": "TEXT",
    "away_team": "TEXT NOT NULL",
    "home_team": "TEXT NOT NULL",
    "market_type": "TEXT NOT NULL",
    "event_id": "TEXT",
    "bookmaker_key": "TEXT",
    "sport_key": "TEXT",
    "commence_time": "TEXT",
    "sportsbook": "TEXT",
    "pick": "TEXT NOT NULL",
    "model_win_probability": "REAL",
    "projected_total": "REAL",
    "locked_line": "REAL",
    "locked_odds": "INTEGER",
    "locked_implied_probability": "REAL",
    "market_implied_probability": "REAL",
    "market_no_vig_probability": "REAL",
    "edge": "REAL",
    "ev": "REAL",
    "best_bet_flag": "TEXT",
    "signal_strength": "TEXT",
    "is_actionable": "INTEGER NOT NULL DEFAULT 0",
    "tracking_mode": "TEXT NOT NULL DEFAULT 'full_visible_board'",
    "edge_bucket": "TEXT",
    "source": "TEXT NOT NULL DEFAULT 'manual'",
    "closing_line": "REAL",
    "closing_odds": "INTEGER",
    "closing_implied_probability": "REAL",
    "closing_captured_at": "TEXT",
    "clv_value": "REAL",
    "clv_direction": "TEXT",
    "close_status": "TEXT",
    "result": "TEXT",
    "units": "REAL",
    "clv": "REAL",
    "final_away_runs": "REAL",
    "final_home_runs": "REAL",
    "graded_at": "TEXT",
    "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
}


def get_db_path() -> Path:
    """Return the database path used by the project."""
    return DB_PATH


def ensure_model_features_columns(connection: sqlite3.Connection) -> None:
    """Add any newer feature columns that are missing from an existing SQLite table."""
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(model_features)").fetchall()
    }

    for column_name, column_type in MODEL_FEATURE_COLUMNS.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE model_features ADD COLUMN {column_name} {column_type}"
        )


def ensure_odds_snapshots_columns(connection: sqlite3.Connection) -> None:
    """Add any newer odds snapshot columns that are missing from an existing table."""
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(odds_snapshots)").fetchall()
    }

    for column_name, column_type in ODDS_SNAPSHOTS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(
            f"ALTER TABLE odds_snapshots ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game_time ON odds_snapshots (game_id, snapshot_time)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_odds_snapshots_game_book_time ON odds_snapshots (game_id, sportsbook_name, snapshot_time)"
    )


def ensure_tracked_bets_columns(connection: sqlite3.Connection) -> None:
    """Add any newer tracked-bet columns that are missing from an existing table."""
    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "tracked_bets" not in existing_tables:
        return

    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(tracked_bets)").fetchall()
    }
    for column_name, column_type in TRACKED_BETS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(
            f"ALTER TABLE tracked_bets ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_tracked_bets_game_id ON tracked_bets (game_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_tracked_bets_match_method ON tracked_bets (game_match_method)"
    )


def ensure_predictions_columns(connection: sqlite3.Connection) -> None:
    """Add any newer prediction columns that are missing from an existing table."""
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(predictions)").fetchall()
    }

    for column_name, column_type in PREDICTIONS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(
            f"ALTER TABLE predictions ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_game_model ON predictions (game_id, model_version)"
    )


def ensure_odds_api_cache_columns(connection: sqlite3.Connection) -> None:
    """Add any newer cache columns that are missing from the odds API cache."""
    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "odds_api_cache" not in existing_tables:
        return

    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(odds_api_cache)").fetchall()
    }
    for column_name, column_type in ODDS_API_CACHE_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(
            f"ALTER TABLE odds_api_cache ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_api_cache_unique ON odds_api_cache (event_id, regions, markets, odds_format)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_odds_api_cache_lookup ON odds_api_cache (sport_key, regions, markets, odds_format, commence_time)"
    )


def ensure_performance_bets_columns(connection: sqlite3.Connection) -> None:
    """Add any newer performance tracking columns that are missing."""
    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    if "performance_bets" not in existing_tables:
        return

    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(performance_bets)").fetchall()
    }
    for column_name, column_type in PERFORMANCE_BETS_COLUMNS.items():
        if column_name in existing_columns:
            continue
        connection.execute(
            f"ALTER TABLE performance_bets ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_performance_bets_game_date ON performance_bets (game_date, snapshot_timestamp)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_performance_bets_market_type ON performance_bets (market_type, signal_strength)"
    )


def initialize_database(db_path: Path | None = None) -> Path:
    """Create the SQLite database and all project tables."""
    target_path = db_path or get_db_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(target_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(SCHEMA_SQL)
        ensure_model_features_columns(connection)
        ensure_odds_snapshots_columns(connection)
        ensure_predictions_columns(connection)
        ensure_tracked_bets_columns(connection)
        ensure_odds_api_cache_columns(connection)
        ensure_performance_bets_columns(connection)
        connection.commit()

    return target_path


def main() -> None:
    db_path = initialize_database()
    print(f"Database initialized at: {db_path}")


if __name__ == "__main__":
    main()
