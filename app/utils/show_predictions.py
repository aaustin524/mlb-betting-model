import sqlite3
from app.config import DB_PATH


def show_predictions(limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = """
    SELECT
        game_id,
        home_win_prob,
        away_win_prob
    FROM predictions
    ORDER BY prediction_time DESC
    LIMIT ?
    """

    cursor.execute(query, (limit,))
    rows = cursor.fetchall()

    print("\nLatest Predictions\n")

    for row in rows:
        game_id, home_prob, away_prob = row
        print(
            f"Game {game_id} | Home Win Prob: {home_prob:.3f} | Away Win Prob: {away_prob:.3f}"
        )

    conn.close()


def main():
    show_predictions()


if __name__ == "__main__":
    main()