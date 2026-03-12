"""Helpers for creating the project folders used in later phases."""

from app.config import MODEL_DIR, PROCESSED_DATA_DIR, RAW_DATA_DIR


def ensure_data_directories() -> None:
    """Create the core data directories if they do not exist yet."""
    for path in (RAW_DATA_DIR, PROCESSED_DATA_DIR, MODEL_DIR):
        path.mkdir(parents=True, exist_ok=True)
