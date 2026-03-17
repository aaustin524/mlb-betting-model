"""Shared project configuration helpers.

This lives at the project root so model modules can import paths without
accidentally pulling in the Streamlit app package and creating circular imports.
"""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODEL_DIR = DATA_DIR / "models"
DEFAULT_DB_PATH = BASE_DIR / "db" / "mlb_betting_model.sqlite"
DB_PATH = Path(os.getenv("MLB_MODEL_DB_PATH", str(DEFAULT_DB_PATH))).expanduser().resolve()
DB_DIR = DB_PATH.parent

# Shared simulation settings
DEFAULT_SIMS = 25000
DEFAULT_RUN_DISPERSION = 6.0

# League run-environment calibration settings
DEFAULT_BASELINE_RUNS_PER_GAME = 9.2
DEFAULT_LOOKBACK_GAMES = 200
DEFAULT_ENVIRONMENT_BLEND_WEIGHT = 0.25

# Starter innings projection settings
MIN_STARTER_INNINGS = 4.0
MAX_STARTER_INNINGS = 7.0
BASELINE_STARTER_INNINGS = 5.5
STARTER_INNINGS_SLOPE = 5.0
REGULATION_INNINGS = 9.0

# Bullpen availability settings
UNAVAILABLE_YESTERDAY_PITCHES = 25
UNAVAILABLE_TWO_DAY_PITCHES = 40
UNAVAILABLE_RELIEVER_PENALTY = 0.03
MAX_KEY_RELIEVERS_COUNTED = 2

# Betting signal thresholds
STRONG_BET_EV_THRESHOLD = 0.05
STRONG_BET_EDGE_THRESHOLD = 5.0
LEAN_BET_EV_THRESHOLD = 0.01
LEAN_BET_EDGE_THRESHOLD = 2.0
STRONG_TOTAL_EV_THRESHOLD = 0.05
STRONG_TOTAL_EDGE_THRESHOLD = 4.0
LEAN_TOTAL_EV_THRESHOLD = 0.01
TOTALS_LOGISTIC_K = 1.35


def get_project_paths() -> dict[str, Path]:
    """Return the main project paths in one beginner-friendly place."""
    return {
        "base_dir": BASE_DIR,
        "data_dir": DATA_DIR,
        "raw_data_dir": RAW_DATA_DIR,
        "processed_data_dir": PROCESSED_DATA_DIR,
        "model_dir": MODEL_DIR,
        "db_dir": DB_DIR,
        "db_path": DB_PATH,
    }
