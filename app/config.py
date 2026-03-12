"""Simple project configuration helpers."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODEL_DIR = DATA_DIR / "models"
DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "mlb_betting_model.sqlite"


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
