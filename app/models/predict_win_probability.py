"""Generate home and away win probabilities from the trained v1 model."""

from __future__ import annotations

import logging
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import DB_PATH
from app.db.schema import initialize_database
from app.models.train_win_probability import MODEL_PATH, V1_FEATURE_COLUMNS

LOGGER = logging.getLogger(__name__)
MODEL_VERSION = "v1_logistic_regression"


def configure_logging() -> None:
    """Configure simple console logging for prediction output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_model(model_path: Path) -> object:
    """Load the trained model from disk."""
    if not model_path.exists():
        raise FileNotFoundError(
            f"Trained model not found at {model_path}. Run app.models.train_win_probability first."
        )

    with model_path.open("rb") as model_file:
        model = pickle.load(model_file)

    LOGGER.info("Loaded trained model from %s", model_path)
    return model


def load_prediction_data(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load the model_features rows needed for v1 predictions."""
    dataset = pd.read_sql_query("SELECT * FROM model_features ORDER BY game_id", connection)
    LOGGER.info("Loaded %s rows from model_features", len(dataset))
    return dataset


def prepare_prediction_frame(dataset: pd.DataFrame) -> pd.DataFrame:
    """Keep the v1 feature columns and the game id used for saving predictions."""
    required_columns = ["game_id"] + V1_FEATURE_COLUMNS

    for column in required_columns:
        if column not in dataset.columns:
            dataset[column] = pd.NA

    prediction_frame = dataset[required_columns].copy()
    if prediction_frame.empty:
        return prediction_frame

    prediction_frame = prediction_frame.dropna(subset=["game_id"])
    prediction_frame["game_id"] = prediction_frame["game_id"].astype(int)
    return prediction_frame


def build_prediction_rows(prediction_frame: pd.DataFrame, model: object) -> list[dict[str, object]]:
    """Generate probability predictions for each game row."""
    if prediction_frame.empty:
        return []

    feature_frame = prediction_frame[V1_FEATURE_COLUMNS]
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
    """Load the trained v1 model, score model_features rows, and save predictions."""
    initialize_database()
    model = load_model(MODEL_PATH)

    with sqlite3.connect(DB_PATH) as connection:
        dataset = load_prediction_data(connection)
        prediction_frame = prepare_prediction_frame(dataset)

        if prediction_frame.empty:
            LOGGER.warning("No model_features rows were found to score.")
            return 0

        prediction_rows = build_prediction_rows(prediction_frame, model)
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
