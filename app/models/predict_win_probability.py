"""Generate home and away win probabilities from the trained v1 model."""

from __future__ import annotations

import logging
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import DB_PATH
from app.db.schema import initialize_database
from app.models.train_win_probability import BASE_FEATURE_COLUMNS, MODEL_PATH

LOGGER = logging.getLogger(__name__)
MODEL_VERSION = "v1_logistic_regression"


def configure_logging() -> None:
    """Configure simple console logging for prediction output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_model_bundle(model_path: Path) -> dict[str, Any]:
    """Load the trained model and its feature columns from disk."""
    if not model_path.exists():
        raise FileNotFoundError(
            f"Trained model not found at {model_path}. Run app.models.train_win_probability first."
        )

    with model_path.open("rb") as model_file:
        loaded_object = pickle.load(model_file)

    if isinstance(loaded_object, dict) and "model" in loaded_object:
        model_bundle = loaded_object
    else:
        model_bundle = {
            "model": loaded_object,
            "feature_columns": BASE_FEATURE_COLUMNS,
        }

    LOGGER.info("Loaded trained model from %s", model_path)
    return model_bundle


def load_prediction_data(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load the model_features rows needed for predictions."""
    dataset = pd.read_sql_query("SELECT * FROM model_features ORDER BY game_id", connection)
    LOGGER.info("Loaded %s rows from model_features", len(dataset))
    return dataset


def prepare_prediction_frame(dataset: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Keep the selected feature columns and the game id used for saving predictions."""
    required_columns = ["game_id"] + feature_columns

    for column in required_columns:
        if column not in dataset.columns:
            dataset[column] = pd.NA

    prediction_frame = dataset[required_columns].copy()
    if prediction_frame.empty:
        return prediction_frame

    prediction_frame = prediction_frame.dropna(subset=["game_id"])
    prediction_frame["game_id"] = prediction_frame["game_id"].astype(int)
    return prediction_frame


def build_prediction_rows(
    prediction_frame: pd.DataFrame,
    model: object,
    feature_columns: list[str],
) -> list[dict[str, object]]:
    """Generate probability predictions for each game row."""
    if prediction_frame.empty:
        return []

    feature_frame = prediction_frame[feature_columns]
    home_win_probs = model.predict_proba(feature_frame)[:, 1]
    prediction_time = datetime.now(timezone.utc).isoformat()

    prediction_rows: list[dict[str, object]] = []
    for game_id, home_win_prob in zip(prediction_frame["game_id"], home_win_probs, strict=False):
        prediction_rows.append(
            {
                "game_id": int(game_id),
                "model_version": MODEL_VERSION,
                "prediction_time": prediction_time,
                "home_win_prob": float(home_win_prob),
                "away_win_prob": float(1.0 - home_win_prob),
            }
        )

    return prediction_rows


def replace_predictions(connection: sqlite3.Connection, prediction_rows: list[dict[str, object]]) -> int:
    """Replace saved predictions for this model version to avoid duplicate rows."""
    if not prediction_rows:
        return 0

    game_ids = [row["game_id"] for row in prediction_rows]
    placeholders = ", ".join("?" for _ in game_ids)
    delete_sql = (
        "DELETE FROM predictions "
        f"WHERE model_version = ? AND game_id IN ({placeholders})"
    )
    connection.execute(delete_sql, [MODEL_VERSION, *game_ids])

    connection.executemany(
        """
        INSERT INTO predictions (
            game_id,
            model_version,
            prediction_time,
            home_win_prob,
            away_win_prob
        )
        VALUES (
            :game_id,
            :model_version,
            :prediction_time,
            :home_win_prob,
            :away_win_prob
        )
        """,
        prediction_rows,
    )
    connection.commit()
    return len(prediction_rows)


def predict_win_probabilities() -> int:
    """Load the trained model, score model_features rows, and save predictions."""
    initialize_database()
    model_bundle = load_model_bundle(MODEL_PATH)
    model = model_bundle["model"]
    feature_columns = list(model_bundle["feature_columns"])

    with sqlite3.connect(DB_PATH) as connection:
        dataset = load_prediction_data(connection)
        prediction_frame = prepare_prediction_frame(dataset, feature_columns)

        if prediction_frame.empty:
            LOGGER.warning("No model_features rows were found to score.")
            return 0

        prediction_rows = build_prediction_rows(prediction_frame, model, feature_columns)
        saved_count = replace_predictions(connection, prediction_rows)

    LOGGER.info("Saved %s prediction rows to the predictions table", saved_count)
    return saved_count


def main() -> None:
    """Run the prediction script."""
    configure_logging()
    saved_count = predict_win_probabilities()
    print(f"Saved {saved_count} predictions to the predictions table in {DB_PATH}")


if __name__ == "__main__":
    main()
