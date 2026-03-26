"""Generate home and away win probabilities from the trained v1 model."""

from __future__ import annotations

import logging
import pickle
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from project_config import DB_PATH
from app.db.schema import initialize_database
from app.models.train_win_probability import BASE_FEATURE_COLUMNS, MODEL_PATH
from app.utils.probabilities import american_to_implied_prob, no_vig_probs

LOGGER = logging.getLogger(__name__)
MODEL_VERSION = "v1_logistic_regression"
RECOMMENDED_BET_EDGE_THRESHOLD = 0.03


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


def load_market_odds_data(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load the latest odds snapshot for each game and sportsbook."""
    query = """
        SELECT
            game_id,
            sportsbook_name,
            snapshot_time,
            home_moneyline,
            away_moneyline
        FROM odds_snapshots
        ORDER BY game_id, sportsbook_name, snapshot_time DESC
    """
    dataset = pd.read_sql_query(query, connection)
    if dataset.empty:
        LOGGER.info("No odds snapshots were found. Market comparison fields will stay empty.")
        return dataset

    latest_snapshots = dataset.drop_duplicates(
        subset=["game_id", "sportsbook_name"],
        keep="first",
    ).reset_index(drop=True)
    LOGGER.info(
        "Loaded %s latest sportsbook odds snapshots across %s games",
        len(latest_snapshots),
        latest_snapshots["game_id"].nunique(),
    )
    return latest_snapshots


def build_market_comparison_lookup(market_odds_df: pd.DataFrame) -> dict[int, dict[str, float | None]]:
    """Build a consensus market-probability snapshot for each game."""
    if market_odds_df.empty:
        return {}

    market_lookup: dict[int, dict[str, float | None]] = {}

    for game_id, game_rows in market_odds_df.groupby("game_id"):
        home_raw_probs: list[float] = []
        away_raw_probs: list[float] = []
        home_no_vig_probs: list[float] = []
        away_no_vig_probs: list[float] = []

        for _, row in game_rows.iterrows():
            home_raw = american_to_implied_prob(row.get("home_moneyline"))
            away_raw = american_to_implied_prob(row.get("away_moneyline"))
            home_no_vig, away_no_vig = no_vig_probs(home_raw, away_raw)

            if home_raw is not None:
                home_raw_probs.append(home_raw)
            if away_raw is not None:
                away_raw_probs.append(away_raw)
            if home_no_vig is not None:
                home_no_vig_probs.append(home_no_vig)
            if away_no_vig is not None:
                away_no_vig_probs.append(away_no_vig)

        market_lookup[int(game_id)] = {
            "market_home_implied_prob_raw": float(sum(home_raw_probs) / len(home_raw_probs))
            if home_raw_probs
            else None,
            "market_away_implied_prob_raw": float(sum(away_raw_probs) / len(away_raw_probs))
            if away_raw_probs
            else None,
            "market_home_implied_prob_no_vig": float(sum(home_no_vig_probs) / len(home_no_vig_probs))
            if home_no_vig_probs
            else None,
            "market_away_implied_prob_no_vig": float(sum(away_no_vig_probs) / len(away_no_vig_probs))
            if away_no_vig_probs
            else None,
        }

    return market_lookup


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
    market_lookup: dict[int, dict[str, float | None]],
) -> list[dict[str, object]]:
    """Generate probability predictions for each game row."""
    if prediction_frame.empty:
        return []

    feature_frame = prediction_frame[feature_columns]
    home_win_probs = model.predict_proba(feature_frame)[:, 1]
    prediction_time = datetime.now(timezone.utc).isoformat()

    prediction_rows: list[dict[str, object]] = []
    for game_id, home_win_prob in zip(prediction_frame["game_id"], home_win_probs):
        away_win_prob = float(1.0 - home_win_prob)
        market_fields = market_lookup.get(int(game_id), {})
        market_home_no_vig = market_fields.get("market_home_implied_prob_no_vig")
        market_away_no_vig = market_fields.get("market_away_implied_prob_no_vig")

        edge_home = (
            float(home_win_prob - market_home_no_vig)
            if market_home_no_vig is not None
            else None
        )
        edge_away = (
            float(away_win_prob - market_away_no_vig)
            if market_away_no_vig is not None
            else None
        )

        recommended_side: str | None = None
        recommended_bet = 0
        positive_edges = {
            "home": edge_home,
            "away": edge_away,
        }
        best_side = max(
            positive_edges,
            key=lambda side: positive_edges[side] if positive_edges[side] is not None else float("-inf"),
        )
        best_edge = positive_edges[best_side]
        if best_edge is not None and best_edge >= RECOMMENDED_BET_EDGE_THRESHOLD:
            recommended_side = best_side
            recommended_bet = 1

        prediction_rows.append(
            {
                "game_id": int(game_id),
                "model_version": MODEL_VERSION,
                "prediction_time": prediction_time,
                "home_win_prob": float(home_win_prob),
                "away_win_prob": away_win_prob,
                "market_home_implied_prob_raw": market_fields.get("market_home_implied_prob_raw"),
                "market_away_implied_prob_raw": market_fields.get("market_away_implied_prob_raw"),
                "market_home_implied_prob_no_vig": market_home_no_vig,
                "market_away_implied_prob_no_vig": market_away_no_vig,
                "edge_home": edge_home,
                "edge_away": edge_away,
                "recommended_side": recommended_side,
                "recommended_bet": recommended_bet,
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
            away_win_prob,
            market_home_implied_prob_raw,
            market_away_implied_prob_raw,
            market_home_implied_prob_no_vig,
            market_away_implied_prob_no_vig,
            edge_home,
            edge_away,
            recommended_side,
            recommended_bet
        )
        VALUES (
            :game_id,
            :model_version,
            :prediction_time,
            :home_win_prob,
            :away_win_prob,
            :market_home_implied_prob_raw,
            :market_away_implied_prob_raw,
            :market_home_implied_prob_no_vig,
            :market_away_implied_prob_no_vig,
            :edge_home,
            :edge_away,
            :recommended_side,
            :recommended_bet
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
        market_odds_df = load_market_odds_data(connection)
        market_lookup = build_market_comparison_lookup(market_odds_df)
        prediction_frame = prepare_prediction_frame(dataset, feature_columns)

        if prediction_frame.empty:
            LOGGER.warning("No model_features rows were found to score.")
            return 0

        prediction_rows = build_prediction_rows(
            prediction_frame,
            model,
            feature_columns,
            market_lookup,
        )
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
