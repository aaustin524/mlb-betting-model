"""Backtest simple side bets from saved model predictions."""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from project_config import DB_PATH
from app.db.schema import initialize_database

LOGGER = logging.getLogger(__name__)
EDGE_THRESHOLD = 0.03


def configure_logging() -> None:
    """Configure simple console logging for backtest output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_backtest_frame(connection: sqlite3.Connection) -> pd.DataFrame:
    """Load completed-game predictions that have market comparison fields."""
    query = """
        SELECT
            p.game_id,
            p.model_version,
            p.home_win_prob,
            p.away_win_prob,
            p.market_home_implied_prob_raw,
            p.market_away_implied_prob_raw,
            p.market_home_implied_prob_no_vig,
            p.market_away_implied_prob_no_vig,
            p.edge_home,
            p.edge_away,
            g.home_score,
            g.away_score
        FROM predictions p
        INNER JOIN games g
            ON g.game_id = p.game_id
        WHERE g.home_score IS NOT NULL
          AND g.away_score IS NOT NULL
        ORDER BY p.game_id
    """
    dataset = pd.read_sql_query(query, connection)
    LOGGER.info("Loaded %s completed prediction rows for backtesting", len(dataset))
    return dataset


def choose_bet_side(row: pd.Series, edge_threshold: float = EDGE_THRESHOLD) -> str | None:
    """Choose the higher-edge side when it clears the minimum threshold."""
    edge_home = row.get("edge_home")
    edge_away = row.get("edge_away")

    best_side: str | None = None
    best_edge = float("-inf")

    if pd.notna(edge_home) and float(edge_home) > best_edge:
        best_side = "home"
        best_edge = float(edge_home)

    if pd.notna(edge_away) and float(edge_away) > best_edge:
        best_side = "away"
        best_edge = float(edge_away)

    if best_side is None or best_edge < edge_threshold:
        return None
    return best_side


def implied_prob_to_profit_multiplier(implied_prob: object) -> float | None:
    """Convert an implied probability into net profit on a 1-unit stake."""
    if implied_prob is None or pd.isna(implied_prob):
        return None

    probability = float(implied_prob)
    if probability <= 0 or probability >= 1:
        return None

    return (1.0 / probability) - 1.0


def simulate_backtest_results(
    predictions_df: pd.DataFrame,
    edge_threshold: float = EDGE_THRESHOLD,
) -> pd.DataFrame:
    """Simulate flat-stake bets from prediction rows."""
    if predictions_df.empty:
        return pd.DataFrame()

    bet_rows: list[dict[str, object]] = []

    for _, row in predictions_df.iterrows():
        selected_side = choose_bet_side(row, edge_threshold=edge_threshold)
        if selected_side is None:
            continue

        selected_prob_raw = row["market_home_implied_prob_raw"]
        did_win = row["home_score"] > row["away_score"]
        if selected_side == "away":
            selected_prob_raw = row["market_away_implied_prob_raw"]
            did_win = row["away_score"] > row["home_score"]

        profit_multiplier = implied_prob_to_profit_multiplier(selected_prob_raw)
        if profit_multiplier is None:
            continue

        units = float(profit_multiplier if did_win else -1.0)
        bet_rows.append(
            {
                "game_id": int(row["game_id"]),
                "selected_side": selected_side,
                "selected_edge": float(row[f"edge_{selected_side}"]),
                "selected_market_implied_prob_raw": float(selected_prob_raw),
                "bet_won": bool(did_win),
                "units": units,
            }
        )

    return pd.DataFrame(bet_rows)


def summarize_backtest_results(results_df: pd.DataFrame) -> dict[str, float]:
    """Return a simple beginner-friendly backtest summary."""
    if results_df.empty:
        return {
            "bets": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "win_rate": 0.0,
            "units": 0.0,
            "roi": 0.0,
        }

    bets = float(len(results_df))
    wins = float(results_df["bet_won"].sum())
    losses = bets - wins
    units = float(results_df["units"].sum())
    return {
        "bets": bets,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / bets if bets else 0.0,
        "units": units,
        "roi": units / bets if bets else 0.0,
    }


def run_backtest(edge_threshold: float = EDGE_THRESHOLD) -> tuple[pd.DataFrame, dict[str, float]]:
    """Run the project backtest from the saved predictions table."""
    initialize_database()

    with sqlite3.connect(DB_PATH) as connection:
        predictions_df = load_backtest_frame(connection)

    results_df = simulate_backtest_results(predictions_df, edge_threshold=edge_threshold)
    summary = summarize_backtest_results(results_df)
    LOGGER.info("Backtest placed %s bets at edge threshold %.2f", int(summary["bets"]), edge_threshold)
    return results_df, summary


def main() -> None:
    """Run the backtest script."""
    configure_logging()
    _, summary = run_backtest()
    print(f"Bets: {int(summary['bets'])}")
    print(f"Wins: {int(summary['wins'])}")
    print(f"Losses: {int(summary['losses'])}")
    print(f"Win Rate: {summary['win_rate']:.4f}")
    print(f"Units: {summary['units']:.4f}")
    print(f"ROI: {summary['roi']:.4f}")


if __name__ == "__main__":
    main()
