"""Train a beginner-friendly home win probability model from SQLite features."""

from __future__ import annotations

import logging
import pickle
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from project_config import DB_PATH, MODEL_DIR
from app.db.schema import initialize_database
from app.features.build_game_features import build_game_features

LOGGER = logging.getLogger(__name__)
MODEL_PATH = MODEL_DIR / "home_win_model.pkl"
BASE_FEATURE_COLUMNS = [
    "home_win_pct_last10",
    "away_win_pct_last10",
    "home_runs_per_game_last14",
    "away_runs_per_game_last14",
    "home_runs_allowed_last14",
    "away_runs_allowed_last14",
    "home_run_diff_last14",
    "away_run_diff_last14",
    "run_diff_edge_last14",
    "home_field_flag",
]
OPTIONAL_STARTER_FEATURE_COLUMNS = [
    "home_starter_era",
    "away_starter_era",
    "home_starter_fip",
    "away_starter_fip",
    "starter_fip_edge",
]
OPTIONAL_BULLPEN_FEATURE_COLUMNS = [
    "home_bullpen_ip_last3",
    "away_bullpen_ip_last3",
    "bullpen_rest_edge",
]
TARGET_COLUMN = "target_home_win"


def configure_logging() -> None:
    """Configure simple console logging for training output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_training_data(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load the v1 training dataset from the model_features table."""
    query = "SELECT * FROM model_features"
    dataset = pd.read_sql_query(query, connection)
    LOGGER.info("Loaded %s rows from model_features", len(dataset))
    return dataset


def add_safe_optional_columns(
    dataset: pd.DataFrame,
    feature_columns: list[str],
    optional_columns: list[str],
) -> None:
    """Append optional columns when they have at least some non-null values."""
    for column in optional_columns:
        if column not in dataset.columns:
            continue

        non_null_count = dataset[column].notna().sum()
        if non_null_count == 0:
            continue

        feature_columns.append(column)


def get_training_feature_columns(dataset: pd.DataFrame) -> list[str]:
    """Choose safe feature columns for the current version of the training dataset."""
    feature_columns = list(BASE_FEATURE_COLUMNS)
    add_safe_optional_columns(dataset, feature_columns, OPTIONAL_STARTER_FEATURE_COLUMNS)
    add_safe_optional_columns(dataset, feature_columns, OPTIONAL_BULLPEN_FEATURE_COLUMNS)
    LOGGER.info("Training with feature columns: %s", ", ".join(feature_columns))
    return feature_columns


def prepare_training_frame(dataset: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    """Keep only the chosen columns and make sure they exist."""
    required_columns = feature_columns + [TARGET_COLUMN]

    for column in required_columns:
        if column not in dataset.columns:
            dataset[column] = pd.NA

    training_frame = dataset[required_columns].copy()
    training_frame = training_frame.dropna(subset=[TARGET_COLUMN])
    training_frame[TARGET_COLUMN] = training_frame[TARGET_COLUMN].astype(int)
    return training_frame


def build_training_pipeline() -> Pipeline:
    """Create a simple scikit-learn pipeline for logistic regression."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
            ("model", LogisticRegression(max_iter=1000)),
        ]
    )


def ensure_model_features_exist(connection: sqlite3.Connection) -> pd.DataFrame:
    """Build v1 features from games when model_features is still empty."""
    dataset = load_training_data(connection)
    if not dataset.empty:
        return dataset

    LOGGER.info("model_features is empty. Building v1 features from the games table now.")
    build_game_features()
    return load_training_data(connection)


def validate_training_frame(training_frame: pd.DataFrame) -> None:
    """Raise clear errors when the dataset is not ready for training."""
    if training_frame.empty:
        raise ValueError("model_features does not contain any rows with target_home_win values.")

    class_count = training_frame[TARGET_COLUMN].nunique()
    if class_count < 2:
        raise ValueError("The training data needs both home wins and home losses to train a model.")

    if len(training_frame) < 5:
        raise ValueError("The training data is too small. Load more games before training the model.")


def save_model(model: Pipeline, feature_columns: list[str], model_path: Path) -> None:
    """Save the trained model and its feature list to disk."""
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_bundle: dict[str, Any] = {
        "model": model,
        "feature_columns": feature_columns,
    }
    with model_path.open("wb") as model_file:
        pickle.dump(model_bundle, model_file)
    LOGGER.info("Saved trained model to %s", model_path)


def train_win_probability_model() -> Path:
    """Train logistic regression on v1 model_features and save the model artifact."""
    initialize_database()

    with sqlite3.connect(DB_PATH) as connection:
        dataset = ensure_model_features_exist(connection)

    feature_columns = get_training_feature_columns(dataset)
    training_frame = prepare_training_frame(dataset, feature_columns)
    validate_training_frame(training_frame)

    x = training_frame[feature_columns]
    y = training_frame[TARGET_COLUMN]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    LOGGER.info("Training rows: %s", len(x_train))
    LOGGER.info("Test rows: %s", len(x_test))

    model_pipeline = build_training_pipeline()
    model_pipeline.fit(x_train, y_train)

    predicted_labels = model_pipeline.predict(x_test)
    predicted_probs = model_pipeline.predict_proba(x_test)[:, 1]

    accuracy = accuracy_score(y_test, predicted_labels)
    loss = log_loss(y_test, predicted_probs)
    roc_auc = roc_auc_score(y_test, predicted_probs)

    print(f"Accuracy: {accuracy:.4f}")
    print(f"Log Loss: {loss:.4f}")
    print(f"ROC AUC: {roc_auc:.4f}")

    save_model(model_pipeline, feature_columns, MODEL_PATH)
    return MODEL_PATH


def main() -> None:
    """Run the model training script."""
    configure_logging()
    model_path = train_win_probability_model()
    print(f"Saved model to {model_path}")


if __name__ == "__main__":
    main()
