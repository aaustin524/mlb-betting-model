"""Shared board data services for Streamlit and Reflex.

Separation of concerns:
- model logic: lives in `model/` and performs simulations / raw calculations
- data shaping: lives here and converts model outputs into board-ready tables
- UI rendering: lives in Streamlit / Reflex files and formats the results

The goal is to keep one source of truth for board-building behavior so both UIs
can call the same services without duplicating business logic.
"""

from __future__ import annotations

import math

import pandas as pd

try:
    from utils.probabilities import american_to_implied_prob
except ModuleNotFoundError:
    from app.utils.probabilities import american_to_implied_prob
from model.game_engine import simulate_matchup
from model.lineup_strength import (
    calculate_lineup_adjustment,
    load_hitter_ratings,
    load_projected_lineups,
)
from model.schedule_loader import load_today_matchups
from model.weather_api import get_weather_for_team
from project_config import (
    DEFAULT_RUN_DISPERSION,
    DEFAULT_SIMS,
    LEAN_BET_EDGE_THRESHOLD,
    LEAN_BET_EV_THRESHOLD,
    LEAN_TOTAL_EV_THRESHOLD,
    STRONG_BET_EDGE_THRESHOLD,
    STRONG_BET_EV_THRESHOLD,
    STRONG_TOTAL_EDGE_THRESHOLD,
    STRONG_TOTAL_EV_THRESHOLD,
    TOTALS_LOGISTIC_K,
)

INPUT_COLUMNS = [
    "Away",
    "Home",
    "Away Pitcher",
    "Home Pitcher",
    "A Hand",
    "H Hand",
    "Away SP",
    "Home SP",
    "Away BP Fatigue",
    "Home BP Fatigue",
    "Away Lineup",
    "Home Lineup",
    "Manual Wx",
    "Temp",
    "Wind",
    "Away Moneyline",
    "Home Moneyline",
    "Total Line",
    "Over Price",
    "Under Price",
    "Sportsbook",
]

RESULT_COLUMNS = [
    "Away Runs",
    "Home Runs",
    "Away Win",
    "Home Win",
    "Away Implied %",
    "Home Implied %",
    "Away No-Vig %",
    "Home No-Vig %",
    "Hold %",
    "Away Consensus %",
    "Home Consensus %",
    "Consensus Hold Avg",
    "Consensus Books Used",
    "Away Fair ML",
    "Home Fair ML",
    "Away Edge %",
    "Home Edge %",
    "Away EV",
    "Home EV",
    "Projected Total",
    "Total Diff",
    "Over Edge %",
    "Under Edge %",
    "Over EV",
    "Under EV",
    "Best Total Bet",
    "Total Bet Flag",
    "Favorite",
    "Win Edge",
    "Best Bet",
    "Bet Flag",
]

MODEL_DETAIL_COLUMNS = [
    "Park",
    "Weather",
]

TABLE_COLUMNS = INPUT_COLUMNS + RESULT_COLUMNS + MODEL_DETAIL_COLUMNS


def load_pitcher_ratings_data(file_path: str = "data/pitcher_ratings.csv") -> pd.DataFrame:
    """Load pitcher ratings in a UI-agnostic shape."""
    pitcher_ratings = pd.read_csv(file_path)
    for required_col, default_value in {
        "pitcher_name": "",
        "pitcher_rating": 1.00,
        "fip": None,
        "throws": "",
    }.items():
        if required_col not in pitcher_ratings.columns:
            pitcher_ratings[required_col] = default_value
    return pitcher_ratings


def load_lineup_data_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load lineup-related data with safe empty fallbacks."""
    try:
        hitter_ratings = load_hitter_ratings()
    except Exception:
        hitter_ratings = pd.DataFrame(columns=["player_name", "hitter_rating"])

    try:
        projected_lineups = load_projected_lineups()
    except Exception:
        projected_lineups = pd.DataFrame(columns=["team", "player_name"])

    return hitter_ratings, projected_lineups


def load_matchups_data(data_mode: str = "local") -> pd.DataFrame:
    """Load today's matchups in a UI-agnostic way."""
    return load_today_matchups(data_mode=data_mode)


def get_default_lineup_adjustment(team_name: str, hitter_ratings: pd.DataFrame, projected_lineups: pd.DataFrame) -> float:
    """Return the lineup multiplier used to seed a daily board row."""
    return calculate_lineup_adjustment(team_name, hitter_ratings, projected_lineups)


def get_default_pitcher_rating(pitcher_name: object, pitcher_ratings: pd.DataFrame) -> float:
    """Return the starter rating default for a pitcher name."""
    if not pitcher_name or pd.isna(pitcher_name):
        return 1.00

    pitcher_row = pitcher_ratings.loc[pitcher_ratings["pitcher_name"] == pitcher_name]
    if pitcher_row.empty:
        return 1.00

    rating = pitcher_row.iloc[0]["pitcher_rating"]
    if pd.isna(rating):
        return 1.00

    return float(rating)


def get_pitcher_throws(pitcher_name: object, pitcher_ratings: pd.DataFrame) -> str:
    """Return pitcher handedness for board display and simulation inputs."""
    if not pitcher_name or pd.isna(pitcher_name):
        return ""

    pitcher_row = pitcher_ratings.loc[pitcher_ratings["pitcher_name"] == pitcher_name]
    if pitcher_row.empty:
        return ""

    throws = pitcher_row.iloc[0]["throws"]
    if pd.isna(throws):
        return ""

    return str(throws).strip().upper()


def get_default_weather(home_team_name: str, stadium_locations: pd.DataFrame, data_mode: str = "local") -> dict[str, float]:
    """Return a plain weather snapshot for default board inputs."""
    weather = get_weather_for_team(
        home_team_name,
        stadium_locations,
        data_mode=data_mode,
    )
    return {
        "Temp": int(weather.get("temperature_f", 72)),
        "Wind": float(weather.get("wind_factor", 1.00)),
    }


def calculate_no_vig_probs(away_odds: object, home_odds: object) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """Convert moneylines to raw and no-vig probabilities."""
    away_raw = american_to_implied_prob(away_odds)
    home_raw = american_to_implied_prob(home_odds)

    if away_raw is None or home_raw is None:
        return away_raw, home_raw, None, None, None

    overround = away_raw + home_raw
    if overround <= 0:
        return away_raw, home_raw, None, None, None

    away_no_vig = away_raw / overround
    home_no_vig = home_raw / overround
    vig = overround - 1.0
    return away_raw, home_raw, away_no_vig, home_no_vig, vig


def american_odds_profit(odds_value: object) -> float | None:
    """Return payout multiple for American odds."""
    if odds_value is None or pd.isna(odds_value):
        return None

    try:
        odds = float(odds_value)
    except (TypeError, ValueError):
        return None

    if odds == 0:
        return None
    if odds > 0:
        return odds / 100.0
    return 100.0 / abs(odds)


def format_moneyline(odds_value: object) -> str:
    """Format a moneyline for plain text tables/cards."""
    if odds_value is None or pd.isna(odds_value):
        return "N/A"

    try:
        odds = int(float(odds_value))
    except (TypeError, ValueError):
        return "N/A"

    if odds > 0:
        return f"+{odds}"
    return str(odds)


def probability_to_american_odds(probability: object) -> int | None:
    """Convert a probability into a fair American moneyline."""
    if probability is None or pd.isna(probability):
        return None

    prob = float(probability)
    if prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return int(round(-100 * prob / (1 - prob)))
    return int(round(100 * (1 - prob) / prob))


def calculate_expected_value(model_win_prob: object, odds_value: object) -> float | None:
    """Calculate bet EV from model win probability and market odds."""
    if model_win_prob is None or pd.isna(model_win_prob):
        return None

    profit = american_odds_profit(odds_value)
    if profit is None:
        return None

    win_prob = float(model_win_prob)
    lose_prob = 1.0 - win_prob
    return (win_prob * profit) - lose_prob


def calculate_total_probabilities(
    projected_total: object,
    total_line: object,
    logistic_k: float = TOTALS_LOGISTIC_K,
) -> tuple[float | None, float | None, float | None]:
    """Turn projected total vs market line into over/under probabilities."""
    if projected_total is None or total_line is None or pd.isna(projected_total) or pd.isna(total_line):
        return None, None, None

    difference = float(projected_total) - float(total_line)
    over_prob = 1.0 / (1.0 + math.exp(-difference * logistic_k))
    under_prob = 1.0 - over_prob
    return over_prob, under_prob, difference


def calculate_totals_market_probs(over_price: object, under_price: object) -> dict[str, float | None]:
    """Return totals-market implied and no-vig probabilities."""
    over_raw = american_to_implied_prob(over_price)
    under_raw = american_to_implied_prob(under_price)
    over_no_vig = None
    under_no_vig = None
    total_hold = None

    if over_raw is not None and under_raw is not None:
        over_raw, under_raw, over_no_vig, under_no_vig, total_hold = calculate_no_vig_probs(
            over_price,
            under_price,
        )

    return {
        "over_raw": over_raw,
        "under_raw": under_raw,
        "over_market_prob": over_no_vig if over_no_vig is not None else over_raw,
        "under_market_prob": under_no_vig if under_no_vig is not None else under_raw,
        "total_hold": total_hold,
    }


def calculate_total_bet_signal(
    over_edge_pct: object,
    under_edge_pct: object,
    over_ev: object,
    under_ev: object,
    strong_ev_threshold: float = STRONG_TOTAL_EV_THRESHOLD,
    strong_edge_threshold: float = STRONG_TOTAL_EDGE_THRESHOLD,
    lean_ev_threshold: float = LEAN_TOTAL_EV_THRESHOLD,
) -> tuple[str, str, float | None, float | None]:
    """Select the best total bet using the existing threshold rules."""
    candidates = [
        {"side": "Over", "edge": over_edge_pct, "ev": over_ev},
        {"side": "Under", "edge": under_edge_pct, "ev": under_ev},
    ]
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate["ev"] is not None and not pd.isna(candidate["ev"]) and candidate["ev"] > 0
    ]
    if not valid_candidates:
        return "Pass", "Pass", None, None

    best_candidate = max(
        valid_candidates,
        key=lambda candidate: (
            candidate["ev"],
            candidate["edge"] if candidate["edge"] is not None else float("-inf"),
        ),
    )
    best_edge = best_candidate["edge"]
    best_ev = best_candidate["ev"]

    if best_ev >= strong_ev_threshold and best_edge is not None and best_edge >= strong_edge_threshold:
        return best_candidate["side"], "Strong Bet", best_edge, best_ev
    if best_ev >= lean_ev_threshold and best_edge is not None and best_edge > 0:
        return best_candidate["side"], "Lean", best_edge, best_ev
    return "Pass", "Pass", best_edge, best_ev


def calculate_bet_signal(
    away_edge_pct: object,
    home_edge_pct: object,
    away_ev: object,
    home_ev: object,
    strong_ev_threshold: float = STRONG_BET_EV_THRESHOLD,
    strong_edge_threshold: float = STRONG_BET_EDGE_THRESHOLD,
    lean_ev_threshold: float = LEAN_BET_EV_THRESHOLD,
    lean_edge_threshold: float = LEAN_BET_EDGE_THRESHOLD,
) -> tuple[str, str, float | None, float | None]:
    """Select the best side bet using the existing threshold rules."""
    candidates = [
        {"side": "Away", "edge": away_edge_pct, "ev": away_ev},
        {"side": "Home", "edge": home_edge_pct, "ev": home_ev},
    ]
    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate["ev"] is not None and not pd.isna(candidate["ev"]) and candidate["ev"] > 0
    ]
    if not valid_candidates:
        return "Pass", "Pass", None, None

    best_candidate = max(
        valid_candidates,
        key=lambda candidate: (
            candidate["ev"],
            candidate["edge"] if candidate["edge"] is not None else float("-inf"),
        ),
    )
    best_edge = best_candidate["edge"]
    best_ev = best_candidate["ev"]

    if best_ev >= strong_ev_threshold and best_edge is not None and best_edge >= strong_edge_threshold:
        return best_candidate["side"], "Strong Bet", best_edge, best_ev
    if best_ev >= lean_ev_threshold and best_edge is not None and best_edge >= lean_edge_threshold:
        return best_candidate["side"], "Lean", best_edge, best_ev
    return "Pass", "Pass", best_edge, best_ev


def build_daily_input_table(
    matchups: pd.DataFrame,
    pitcher_ratings: pd.DataFrame,
    stadium_locations: pd.DataFrame,
    hitter_ratings: pd.DataFrame,
    projected_lineups: pd.DataFrame,
    team_ratings: pd.DataFrame,
    data_mode: str = "local",
) -> pd.DataFrame:
    """Build one editable daily board input row per matchup.

    This is shaping logic, not simulation logic. It seeds the UI with default
    ratings, lineup adjustments, and weather values before a UI renders them.
    """
    rows = []
    for _, matchup in matchups.iterrows():
        away_team_name = matchup.get("away_team", "")
        home_team_name = matchup.get("home_team", "")

        if away_team_name not in team_ratings.index or home_team_name not in team_ratings.index:
            continue

        away_pitcher_name = matchup.get("away_pitcher", "")
        home_pitcher_name = matchup.get("home_pitcher", "")
        if pd.isna(away_pitcher_name):
            away_pitcher_name = ""
        if pd.isna(home_pitcher_name):
            home_pitcher_name = ""

        default_weather = get_default_weather(home_team_name, stadium_locations, data_mode=data_mode)

        rows.append(
            {
                "Away": away_team_name,
                "Home": home_team_name,
                "Away Pitcher": away_pitcher_name,
                "Home Pitcher": home_pitcher_name,
                "A Hand": get_pitcher_throws(away_pitcher_name, pitcher_ratings),
                "H Hand": get_pitcher_throws(home_pitcher_name, pitcher_ratings),
                "Away SP": get_default_pitcher_rating(away_pitcher_name, pitcher_ratings),
                "Home SP": get_default_pitcher_rating(home_pitcher_name, pitcher_ratings),
                "Away BP Fatigue": 0.00,
                "Home BP Fatigue": 0.00,
                "Away Lineup": get_default_lineup_adjustment(away_team_name, hitter_ratings, projected_lineups),
                "Home Lineup": get_default_lineup_adjustment(home_team_name, hitter_ratings, projected_lineups),
                "Manual Wx": False,
                "Temp": default_weather["Temp"],
                "Wind": default_weather["Wind"],
                "Away Moneyline": None,
                "Home Moneyline": None,
                "Total Line": None,
                "Over Price": None,
                "Under Price": None,
                "Sportsbook": None,
            }
        )

    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def build_display_dataframe(
    daily_board_inputs: pd.DataFrame,
    pitcher_ratings: pd.DataFrame,
    team_ratings: pd.DataFrame,
    normalize_team_name_fn,
    live_odds_market_data: dict | None = None,
    run_dispersion: float = DEFAULT_RUN_DISPERSION,
    sims: int = DEFAULT_SIMS,
) -> pd.DataFrame:
    """Build the main board dataframe from model outputs and market inputs.

    This function intentionally stays UI-agnostic. It returns a dataframe that
    either UI can format however it wants.
    """
    display_rows = []
    for _, row in daily_board_inputs.iterrows():
        away_pitcher_name = row["Away Pitcher"]
        home_pitcher_name = row["Home Pitcher"]

        away_pitcher_throws = get_pitcher_throws(away_pitcher_name, pitcher_ratings)
        home_pitcher_throws = get_pitcher_throws(home_pitcher_name, pitcher_ratings)
        row_temperature_f = float(row["Temp"]) if bool(row["Manual Wx"]) else None
        row_wind_factor = float(row["Wind"]) if bool(row["Manual Wx"]) else None

        matchup_results = simulate_matchup(
            away_team=row["Away"],
            home_team=row["Home"],
            away_starter_rating=float(row["Away SP"]),
            home_starter_rating=float(row["Home SP"]),
            away_pitcher_throws=away_pitcher_throws or None,
            home_pitcher_throws=home_pitcher_throws or None,
            away_bullpen_fatigue=float(row["Away BP Fatigue"]),
            home_bullpen_fatigue=float(row["Home BP Fatigue"]),
            away_lineup_adjustment=float(row["Away Lineup"]),
            home_lineup_adjustment=float(row["Home Lineup"]),
            temperature_f=row_temperature_f,
            wind_factor=row_wind_factor,
            sims=sims,
            run_dispersion=run_dispersion,
            teams=team_ratings,
        )

        away_win_pct = round(matchup_results["away_win_prob"] * 100, 1)
        home_win_pct = round(matchup_results["home_win_prob"] * 100, 1)
        matchup_key = (normalize_team_name_fn(row["Away"]), normalize_team_name_fn(row["Home"]))
        market_data = (live_odds_market_data or {}).get(matchup_key, {})

        away_implied_prob, home_implied_prob, away_no_vig_prob, home_no_vig_prob, vig = calculate_no_vig_probs(
            row.get("Away Moneyline"),
            row.get("Home Moneyline"),
        )
        away_implied_pct = round(away_implied_prob * 100, 1) if away_implied_prob is not None else None
        home_implied_pct = round(home_implied_prob * 100, 1) if home_implied_prob is not None else None
        away_no_vig_pct = round(away_no_vig_prob * 100, 1) if away_no_vig_prob is not None else None
        home_no_vig_pct = round(home_no_vig_prob * 100, 1) if home_no_vig_prob is not None else None
        hold_pct = round(vig * 100, 1) if vig is not None else None

        away_consensus_prob = market_data.get("away_consensus_prob")
        home_consensus_prob = market_data.get("home_consensus_prob")
        away_consensus_pct = round(float(away_consensus_prob) * 100, 1) if away_consensus_prob is not None else None
        home_consensus_pct = round(float(home_consensus_prob) * 100, 1) if home_consensus_prob is not None else None

        consensus_hold_avg = market_data.get("consensus_hold_avg")
        consensus_hold_pct = round(float(consensus_hold_avg) * 100, 1) if consensus_hold_avg is not None else None
        consensus_books_used = market_data.get("consensus_books_used")
        away_fair_ml = market_data.get("away_fair_ml")
        home_fair_ml = market_data.get("home_fair_ml")

        away_edge_pct = round(away_win_pct - away_consensus_pct, 1) if away_consensus_pct is not None else None
        home_edge_pct = round(home_win_pct - home_consensus_pct, 1) if home_consensus_pct is not None else None

        away_ev = calculate_expected_value(matchup_results["away_win_prob"], row.get("Away Moneyline"))
        home_ev = calculate_expected_value(matchup_results["home_win_prob"], row.get("Home Moneyline"))
        away_ev_pct = round(away_ev * 100, 1) if away_ev is not None else None
        home_ev_pct = round(home_ev * 100, 1) if home_ev is not None else None

        projected_total = round(matchup_results["away_lambda"] + matchup_results["home_lambda"], 2)
        over_prob, under_prob, total_difference = calculate_total_probabilities(projected_total, row.get("Total Line"))
        totals_market = calculate_totals_market_probs(
            row.get("Over Price"),
            row.get("Under Price"),
        )
        over_market_prob = totals_market["over_market_prob"]
        under_market_prob = totals_market["under_market_prob"]

        over_edge_pct = round((over_prob - over_market_prob) * 100, 1) if over_prob is not None and over_market_prob is not None else None
        under_edge_pct = round((under_prob - under_market_prob) * 100, 1) if under_prob is not None and under_market_prob is not None else None

        over_ev = calculate_expected_value(over_prob, row.get("Over Price")) if over_prob is not None else None
        under_ev = calculate_expected_value(under_prob, row.get("Under Price")) if under_prob is not None else None
        over_ev_pct = round(over_ev * 100, 1) if over_ev is not None else None
        under_ev_pct = round(under_ev * 100, 1) if under_ev is not None else None

        best_total_bet, total_bet_flag, _, _ = calculate_total_bet_signal(
            over_edge_pct,
            under_edge_pct,
            over_ev,
            under_ev,
        )
        best_bet, bet_flag, _, _ = calculate_bet_signal(
            away_edge_pct,
            home_edge_pct,
            away_ev,
            home_ev,
        )

        display_row = row.to_dict()
        display_row["A Hand"] = away_pitcher_throws
        display_row["H Hand"] = home_pitcher_throws
        display_row["Away Runs"] = round(matchup_results["away_lambda"], 2)
        display_row["Home Runs"] = round(matchup_results["home_lambda"], 2)
        display_row["Away Win"] = away_win_pct
        display_row["Home Win"] = home_win_pct
        display_row["Away Implied %"] = away_implied_pct
        display_row["Home Implied %"] = home_implied_pct
        display_row["Away No-Vig %"] = away_no_vig_pct
        display_row["Home No-Vig %"] = home_no_vig_pct
        display_row["Hold %"] = hold_pct
        display_row["Away Consensus %"] = away_consensus_pct
        display_row["Home Consensus %"] = home_consensus_pct
        display_row["Consensus Hold Avg"] = consensus_hold_pct
        display_row["Consensus Books Used"] = consensus_books_used
        display_row["Away Fair ML"] = away_fair_ml
        display_row["Home Fair ML"] = home_fair_ml
        display_row["Away Edge %"] = away_edge_pct
        display_row["Home Edge %"] = home_edge_pct
        display_row["Away EV"] = away_ev_pct
        display_row["Home EV"] = home_ev_pct
        display_row["Projected Total"] = projected_total
        display_row["Total Diff"] = round(total_difference, 2) if total_difference is not None else None
        display_row["Over Edge %"] = over_edge_pct
        display_row["Under Edge %"] = under_edge_pct
        display_row["Over EV"] = over_ev_pct
        display_row["Under EV"] = under_ev_pct
        display_row["Best Total Bet"] = best_total_bet
        display_row["Total Bet Flag"] = total_bet_flag
        display_row["Favorite"] = row["Home"] if home_win_pct >= away_win_pct else row["Away"]
        display_row["Win Edge"] = round(abs(home_win_pct - away_win_pct), 1)
        display_row["Best Bet"] = row["Away"] if best_bet == "Away" else row["Home"] if best_bet == "Home" else "Pass"
        display_row["Bet Flag"] = bet_flag
        display_row["Park"] = round(matchup_results["park_factor"], 2)
        display_row["Weather"] = round(matchup_results["weather_multiplier"], 2)
        display_rows.append(display_row)

    return pd.DataFrame(display_rows, columns=TABLE_COLUMNS)


def _flag_priority(flag_value: object) -> int:
    return {
        "Strong Bet": 2,
        "Lean": 1,
        "Pass": 0,
    }.get(flag_value, 0)


def _build_side_candidate(row: pd.Series) -> dict[str, object] | None:
    pick = row.get("Best Bet")
    flag_value = row.get("Bet Flag")
    if flag_value not in {"Lean", "Strong Bet"} or pick == "Pass" or pd.isna(pick):
        return None

    if pick == row.get("Away"):
        line_value = row.get("Away Moneyline")
        ev_value = row.get("Away EV")
        edge_value = row.get("Away Edge %")
    elif pick == row.get("Home"):
        line_value = row.get("Home Moneyline")
        ev_value = row.get("Home EV")
        edge_value = row.get("Home Edge %")
    else:
        return None

    if ev_value is None or pd.isna(ev_value):
        return None

    return {
        "matchup": f"{row['Away']} at {row['Home']}",
        "bet_type": "Side",
        "pick": pick,
        "sportsbook": row.get("Sportsbook") if pd.notna(row.get("Sportsbook")) else "N/A",
        "line": format_moneyline(line_value),
        "model_edge": float(edge_value) if edge_value is not None and not pd.isna(edge_value) else None,
        "ev": float(ev_value),
        "flag": flag_value,
        "projected_total": None,
        "market_total": None,
    }


def _build_total_candidate(row: pd.Series) -> dict[str, object] | None:
    pick = row.get("Best Total Bet")
    flag_value = row.get("Total Bet Flag")
    if flag_value not in {"Lean", "Strong Bet"} or pick == "Pass" or pd.isna(pick):
        return None

    if pick == "Over":
        line_value = row.get("Over Price")
        ev_value = row.get("Over EV")
        edge_value = row.get("Over Edge %")
    elif pick == "Under":
        line_value = row.get("Under Price")
        ev_value = row.get("Under EV")
        edge_value = row.get("Under Edge %")
    else:
        return None

    if ev_value is None or pd.isna(ev_value):
        return None

    market_total = row.get("Total Line")
    projected_total = row.get("Projected Total")
    line_label = f"{pick} {float(market_total):.1f}" if market_total is not None and not pd.isna(market_total) else pick

    return {
        "matchup": f"{row['Away']} at {row['Home']}",
        "bet_type": "Total",
        "pick": pick,
        "sportsbook": row.get("Sportsbook") if pd.notna(row.get("Sportsbook")) else "N/A",
        "line": f"{line_label} ({format_moneyline(line_value)})",
        "model_edge": float(edge_value) if edge_value is not None and not pd.isna(edge_value) else None,
        "ev": float(ev_value),
        "flag": flag_value,
        "projected_total": float(projected_total) if projected_total is not None and not pd.isna(projected_total) else None,
        "market_total": float(market_total) if market_total is not None and not pd.isna(market_total) else None,
    }


def build_top_plays_dataframe(display_df: pd.DataFrame, max_plays: int = 5) -> pd.DataFrame:
    """Build a sorted top-plays table from the shared display dataframe."""
    candidates = []
    for _, row in display_df.iterrows():
        side_candidate = _build_side_candidate(row)
        if side_candidate is not None:
            candidates.append(side_candidate)

        total_candidate = _build_total_candidate(row)
        if total_candidate is not None:
            candidates.append(total_candidate)

    if not candidates:
        return pd.DataFrame(
            columns=[
                "matchup",
                "bet_type",
                "pick",
                "sportsbook",
                "line",
                "model_edge",
                "ev",
                "flag",
                "projected_total",
                "market_total",
            ]
        )

    candidates_df = pd.DataFrame(candidates)
    candidates_df["flag_priority"] = candidates_df["flag"].map(_flag_priority)
    candidates_df["ev"] = pd.to_numeric(candidates_df["ev"], errors="coerce")
    candidates_df["model_edge"] = pd.to_numeric(candidates_df["model_edge"], errors="coerce")
    candidates_df = candidates_df.sort_values(
        by=["flag_priority", "ev", "model_edge"],
        ascending=[False, False, False],
        na_position="last",
    ).head(max_plays)
    return candidates_df.reset_index(drop=True)


def build_summary_metrics(display_df: pd.DataFrame) -> dict[str, object]:
    """Build plain summary metrics for a board overview."""
    games_today = len(display_df)
    if games_today == 0:
        return {
            "games_today": 0,
            "avg_total_runs": "0.00",
            "strongest_ev": "No games loaded",
            "strongest_ev_delta": "",
            "playable_bets": 0,
            "playable_total_bets": 0,
        }

    avg_total_runs = (display_df["Away Runs"] + display_df["Home Runs"]).mean()
    betting_df = display_df[
        ["Away", "Home", "Away Edge %", "Home Edge %", "Away EV", "Home EV", "Best Bet", "Bet Flag"]
    ].copy()
    betting_df["Away Edge %"] = pd.to_numeric(betting_df["Away Edge %"], errors="coerce")
    betting_df["Home Edge %"] = pd.to_numeric(betting_df["Home Edge %"], errors="coerce")
    betting_df["Away EV"] = pd.to_numeric(betting_df["Away EV"], errors="coerce")
    betting_df["Home EV"] = pd.to_numeric(betting_df["Home EV"], errors="coerce")

    strongest_ev_text = "No positive EV spots"
    strongest_ev_delta = ""
    positive_away = betting_df["Away EV"].where(betting_df["Away EV"] > 0)
    positive_home = betting_df["Home EV"].where(betting_df["Home EV"] > 0)

    if not pd.isna(positive_away).all() or not pd.isna(positive_home).all():
        away_best_idx = positive_away.idxmax() if not pd.isna(positive_away).all() else None
        home_best_idx = positive_home.idxmax() if not pd.isna(positive_home).all() else None
        away_best_ev = positive_away.loc[away_best_idx] if away_best_idx is not None else None
        home_best_ev = positive_home.loc[home_best_idx] if home_best_idx is not None else None

        if away_best_ev is not None and not pd.isna(away_best_ev) and (
            home_best_ev is None or pd.isna(home_best_ev) or away_best_ev >= home_best_ev
        ):
            strongest_ev_text = f"{betting_df.loc[away_best_idx, 'Away']} away"
            strongest_ev_delta = f"{away_best_ev:.1f}% EV"
        elif home_best_ev is not None and not pd.isna(home_best_ev):
            strongest_ev_text = f"{betting_df.loc[home_best_idx, 'Home']} home"
            strongest_ev_delta = f"{home_best_ev:.1f}% EV"

    playable_bets = int(display_df["Bet Flag"].isin(["Lean", "Strong Bet"]).sum())
    playable_total_bets = int(display_df["Total Bet Flag"].isin(["Lean", "Strong Bet"]).sum())

    return {
        "games_today": games_today,
        "avg_total_runs": f"{avg_total_runs:.2f}",
        "strongest_ev": strongest_ev_text,
        "strongest_ev_delta": strongest_ev_delta,
        "playable_bets": playable_bets,
        "playable_total_bets": playable_total_bets,
    }
