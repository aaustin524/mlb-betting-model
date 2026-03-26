"""Manual performance tracking helpers for Reflex paper-bet workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from app.db.connection import get_connection
from app.db.schema import initialize_database
from app.services.board_data import calculate_total_probabilities, calculate_totals_market_probs
from model.clv_tracker import (
    american_odds_to_implied_prob,
    american_odds_profit,
    calculate_side_clv_metrics,
    calculate_total_clv_metrics,
    choose_preferred_bookmaker,
    normalize_sportsbook_name,
    parse_bookmaker_h2h_market,
    parse_bookmaker_totals_market,
)
from reflex_app.services.live_odds import get_event_market_snapshot, read_cached_odds_rows


PERFORMANCE_TABLE = "performance_bets"
TRACKING_MODES = {"full_visible_board", "model_leans_only", "actionable_only"}
EDGE_BUCKETS = [
    (8.0, "8%+"),
    (5.0, "5-8%"),
    (2.0, "2-5%"),
    (0.0, "0-2%"),
]
PRE_CLOSE_CAPTURE_WINDOW_MINUTES = 60
RECENT_START_CAPTURE_WINDOW_MINUTES = 180
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
RECENT_RESULTS_LOOKBACK_DAYS = 7


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _coerce_actionable_flag(value: Any) -> int:
    if value in (None, "") or pd.isna(value):
        return 0
    try:
        return 1 if int(float(value)) else 0
    except (TypeError, ValueError):
        return 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_local_iso() -> str:
    return datetime.now().date().isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, "") or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _display_timestamp(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return parsed.astimezone().strftime("%b %d, %I:%M %p")


def _edge_bucket(edge_value: float | None) -> str:
    edge_abs = abs(edge_value or 0.0)
    for threshold, label in EDGE_BUCKETS:
        if edge_abs >= threshold:
            return label
    return "0-2%"


def _close_signal_from_clv(clv_value: float | None) -> str:
    if clv_value is None:
        return "Flat"
    if clv_value > 0.009:
        return "Beat Close"
    if clv_value < -0.009:
        return "Missed Close"
    return "Flat"


def _clv_direction_label(clv_value: float | None) -> str:
    if clv_value is None:
        return "Flat"
    if clv_value > 0.009:
        return "Positive CLV"
    if clv_value < -0.009:
        return "Negative CLV"
    return "Flat"


def _build_tracking_key(snapshot_timestamp: str, away_team: str, home_team: str, market_type: str) -> str:
    return f"{snapshot_timestamp}|{away_team}|{home_team}|{market_type}"


def _normalize_tracking_mode(tracking_mode: str | None) -> str:
    mode = str(tracking_mode or "").strip().lower()
    return mode if mode in TRACKING_MODES else "full_visible_board"


def _normalize_team_name(team_name: Any) -> str:
    if team_name is None or pd.isna(team_name):
        return ""
    normalized = str(team_name).strip().lower()
    for old_value, new_value in {
        ".": "",
        ",": "",
        "'": "",
        "-": " ",
    }.items():
        normalized = normalized.replace(old_value, new_value)
    normalized = " ".join(token for token in normalized.split() if token not in {"the"})
    if normalized == "athletics":
        return "oakland athletics"
    return normalized


def _fetch_recent_final_games(days_back: int = RECENT_RESULTS_LOOKBACK_DAYS) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]]]:
    """Fetch a short window of recent final MLB games for grading/linking refresh."""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=max(days_back, 1))
    response = requests.get(
        MLB_SCHEDULE_URL,
        params={
            "sportId": 1,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "hydrate": "team",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    teams_by_id: dict[int, tuple[int, str, str]] = {}
    game_rows: list[tuple[Any, ...]] = []
    for day in payload.get("dates", []):
        game_date = day.get("date")
        for game in day.get("games", []):
            status = game.get("status", {})
            abstract_state = str(status.get("abstractGameState") or "").strip()
            detailed_state = str(status.get("detailedState") or "").strip()
            if abstract_state != "Final" and detailed_state != "Final":
                continue

            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            home_team = home.get("team", {}) or {}
            away_team = away.get("team", {}) or {}
            home_team_id = home_team.get("id")
            away_team_id = away_team.get("id")
            home_score = home.get("score")
            away_score = away.get("score")
            if None in {home_team_id, away_team_id, home_score, away_score}:
                continue

            teams_by_id[int(home_team_id)] = (
                int(home_team_id),
                str(home_team.get("name") or f"Team {home_team_id}"),
                str(home_team.get("abbreviation") or f"T{home_team_id}"),
            )
            teams_by_id[int(away_team_id)] = (
                int(away_team_id),
                str(away_team.get("name") or f"Team {away_team_id}"),
                str(away_team.get("abbreviation") or f"T{away_team_id}"),
            )
            game_rows.append(
                (
                    int(game.get("gamePk")),
                    str(game_date or ""),
                    int(pd.to_datetime(game_date, errors="coerce").year) if game_date else datetime.now().year,
                    detailed_state or abstract_state or "Final",
                    int(home_team_id),
                    int(away_team_id),
                    int(home_score),
                    int(away_score),
                    None,
                    None,
                )
            )

    return list(teams_by_id.values()), game_rows


def _refresh_recent_final_games(days_back: int = RECENT_RESULTS_LOOKBACK_DAYS) -> None:
    """Backfill recent completed games so grading can resolve yesterday's bets."""
    try:
        team_rows, game_rows = _fetch_recent_final_games(days_back=days_back)
    except requests.RequestException as exc:
        print(f"[Reflex Performance] Recent final games refresh failed: {exc}")
        return

    if not team_rows and not game_rows:
        return

    initialize_database()
    with get_connection() as connection:
        if team_rows:
            connection.executemany(
                """
                INSERT INTO teams (team_id, team_name, team_abbr)
                VALUES (?, ?, ?)
                ON CONFLICT(team_id) DO UPDATE SET
                    team_name = excluded.team_name,
                    team_abbr = excluded.team_abbr
                """,
                team_rows,
            )
        if game_rows:
            connection.executemany(
                """
                INSERT INTO games (
                    game_id,
                    game_date,
                    season,
                    status,
                    home_team_id,
                    away_team_id,
                    home_score,
                    away_score,
                    home_starting_pitcher_id,
                    away_starting_pitcher_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    game_date = excluded.game_date,
                    season = excluded.season,
                    status = excluded.status,
                    home_team_id = excluded.home_team_id,
                    away_team_id = excluded.away_team_id,
                    home_score = excluded.home_score,
                    away_score = excluded.away_score
                """,
                game_rows,
            )
        connection.commit()


def _relink_open_performance_bets() -> int:
    """Attach game ids to open paper bets after refreshing the recent games table."""
    initialize_database()
    with get_connection() as connection:
        open_df = pd.read_sql_query(
            f"""
            SELECT performance_bet_id, away_team, home_team, game_date
            FROM {PERFORMANCE_TABLE}
            WHERE graded_at IS NULL
              AND (game_id IS NULL OR TRIM(COALESCE(game_match_method, '')) IN ('', 'unmatched'))
            """,
            connection,
        )
        if open_df.empty:
            return 0

        updated_rows = 0
        for _, row in open_df.iterrows():
            game_id, match_method = _match_game_id(
                str(row.get("away_team") or ""),
                str(row.get("home_team") or ""),
                str(row.get("game_date") or ""),
            )
            if game_id is None:
                continue
            connection.execute(
                f"""
                UPDATE {PERFORMANCE_TABLE}
                SET game_id = ?,
                    game_match_method = ?,
                    updated_at = ?
                WHERE performance_bet_id = ?
                """,
                (game_id, match_method, _utc_now_iso(), int(row["performance_bet_id"])),
            )
            updated_rows += 1
        connection.commit()
        return updated_rows


def _is_actionable_signal(signal_strength: str | None) -> bool:
    return str(signal_strength or "").strip() in {"Lean", "Strong Bet"}


def _derive_side_pick(board_row: dict[str, str], tracking_mode: str) -> tuple[str | None, bool]:
    away_team = str(board_row.get("Away", "")).strip()
    home_team = str(board_row.get("Home", "")).strip()
    signal_strength = str(board_row.get("Bet Flag", "")).strip()
    best_bet = str(board_row.get("Best Bet", "")).strip()
    is_actionable = _is_actionable_signal(signal_strength) and best_bet not in {"", "Pass"}
    if tracking_mode == "actionable_only":
        return (best_bet if is_actionable else None), is_actionable

    if is_actionable:
        return best_bet, True

    away_win = _to_float(board_row.get("Away Win"))
    home_win = _to_float(board_row.get("Home Win"))
    if away_win is None and home_win is None:
        return None, False
    if away_win is None:
        return home_team or None, False
    if home_win is None:
        return away_team or None, False
    if away_win >= home_win:
        return away_team or None, False
    return home_team or None, False


def _derive_total_pick(board_row: dict[str, str], tracking_mode: str) -> tuple[str | None, bool]:
    signal_strength = str(board_row.get("Total Bet Flag", "")).strip()
    best_total_bet = str(board_row.get("Best Total Bet", "")).strip()
    is_actionable = _is_actionable_signal(signal_strength) and best_total_bet not in {"", "Pass"}
    if tracking_mode == "actionable_only":
        return (best_total_bet if is_actionable else None), is_actionable

    if is_actionable:
        return best_total_bet, True

    total_line = _to_float(board_row.get("Total Line"))
    projected_total = _to_float(board_row.get("Projected Total"))
    if total_line is None or projected_total is None:
        return None, False
    if projected_total > total_line:
        return "Over", False
    if projected_total < total_line:
        return "Under", False
    if tracking_mode == "full_visible_board":
        return "Over", False
    return None, False


def _load_game_lookup() -> list[dict[str, Any]]:
    initialize_database()
    query = """
        SELECT
            games.game_id,
            games.game_date,
            home_teams.team_name AS home_team_name,
            away_teams.team_name AS away_team_name
        FROM games
        JOIN teams AS home_teams ON games.home_team_id = home_teams.team_id
        JOIN teams AS away_teams ON games.away_team_id = away_teams.team_id
    """
    with get_connection() as connection:
        games_df = pd.read_sql_query(query, connection)

    rows: list[dict[str, Any]] = []
    for _, row in games_df.iterrows():
        game_date = pd.to_datetime(row.get("game_date"), errors="coerce")
        if pd.isna(game_date):
            continue
        rows.append(
            {
                "game_id": int(row["game_id"]),
                "game_date": game_date.date().isoformat(),
                "away_team_key": _normalize_team_name(row.get("away_team_name")),
                "home_team_key": _normalize_team_name(row.get("home_team_name")),
            }
        )
    return rows


def _match_game_id(away_team: str, home_team: str, game_date: str | None) -> tuple[int | None, str]:
    away_key = _normalize_team_name(away_team)
    home_key = _normalize_team_name(home_team)
    if not away_key or not home_key or not game_date:
        return None, "unmatched"

    target_date = pd.to_datetime(game_date, errors="coerce")
    if pd.isna(target_date):
        return None, "unmatched"

    candidates = [
        row
        for row in _load_game_lookup()
        if row["away_team_key"] == away_key and row["home_team_key"] == home_key
    ]
    if not candidates:
        return None, "unmatched"

    exact = [row for row in candidates if row["game_date"] == target_date.date().isoformat()]
    if len(exact) == 1:
        return int(exact[0]["game_id"]), "exact_date"
    if len(exact) > 1:
        return None, "ambiguous"

    adjacent_dates = {
        (target_date - timedelta(days=1)).date().isoformat(),
        (target_date + timedelta(days=1)).date().isoformat(),
    }
    adjacent = [row for row in candidates if row["game_date"] in adjacent_dates]
    if len(adjacent) == 1:
        return int(adjacent[0]["game_id"]), "adjacent_date"
    if len(adjacent) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _build_side_snapshot_row(
    board_row: dict[str, str],
    snapshot_timestamp: str,
    game_date: str,
    tracking_mode: str,
) -> dict[str, Any] | None:
    signal_strength = str(board_row.get("Bet Flag", "")).strip() or "Pass"
    pick, is_actionable = _derive_side_pick(board_row, tracking_mode)
    if pick in {None, "", "Pass"}:
        return None

    away_team = str(board_row.get("Away", "")).strip()
    home_team = str(board_row.get("Home", "")).strip()
    is_away = pick == away_team
    locked_odds = _to_int(board_row.get("Away Moneyline" if is_away else "Home Moneyline"))
    if locked_odds is None:
        return None

    implied_probability = _to_float(board_row.get("Away Implied %" if is_away else "Home Implied %"))
    no_vig_probability = _to_float(board_row.get("Away No-Vig %" if is_away else "Home No-Vig %"))
    model_probability = _to_float(board_row.get("Away Win" if is_away else "Home Win"))
    edge = _to_float(board_row.get("Away Edge %" if is_away else "Home Edge %"))
    ev = _to_float(board_row.get("Away EV" if is_away else "Home EV"))
    game_id, match_method = _match_game_id(away_team, home_team, game_date)

    return {
        "tracking_key": _build_tracking_key(snapshot_timestamp, away_team, home_team, "moneyline"),
        "snapshot_group_id": snapshot_timestamp,
        "snapshot_timestamp": snapshot_timestamp,
        "game_date": game_date,
        "game_id": game_id,
        "game_match_method": match_method,
        "away_team": away_team,
        "home_team": home_team,
        "market_type": "moneyline",
        "event_id": str(board_row.get("Event Id", "")).strip() or None,
        "bookmaker_key": str(board_row.get("Bookmaker Key", "")).strip() or None,
        "sport_key": str(board_row.get("Sport Key", "")).strip() or "baseball_mlb",
        "commence_time": str(board_row.get("Commence Time", "")).strip() or None,
        "sportsbook": str(board_row.get("Sportsbook", "")).strip() or None,
        "pick": pick,
        "model_win_probability": None if model_probability is None else model_probability / 100.0,
        "projected_total": _to_float(board_row.get("Projected Total")),
        "locked_line": None,
        "locked_odds": locked_odds,
        "locked_implied_probability": None if implied_probability is None else implied_probability / 100.0,
        "market_implied_probability": None if implied_probability is None else implied_probability / 100.0,
        "market_no_vig_probability": None if no_vig_probability is None else no_vig_probability / 100.0,
        "edge": edge,
        "ev": None if ev is None else ev / 100.0,
        "best_bet_flag": pick,
        "signal_strength": signal_strength,
        "is_actionable": 1 if is_actionable else 0,
        "tracking_mode": tracking_mode,
        "edge_bucket": _edge_bucket(edge),
        "closing_implied_probability": None,
        "closing_captured_at": None,
        "clv_value": None,
        "clv_direction": "Flat",
        "close_status": "Awaiting Close",
        "source": "manual",
    }


def _build_total_snapshot_row(
    board_row: dict[str, str],
    snapshot_timestamp: str,
    game_date: str,
    tracking_mode: str,
) -> dict[str, Any] | None:
    signal_strength = str(board_row.get("Total Bet Flag", "")).strip() or "Pass"
    pick, is_actionable = _derive_total_pick(board_row, tracking_mode)
    if pick in {None, "", "Pass"}:
        return None

    total_line = _to_float(board_row.get("Total Line"))
    locked_odds = _to_int(board_row.get("Over Price" if pick == "Over" else "Under Price"))
    projected_total = _to_float(board_row.get("Projected Total"))
    if total_line is None or projected_total is None:
        return None

    over_prob, under_prob, _ = calculate_total_probabilities(projected_total, total_line)
    totals_market = calculate_totals_market_probs(
        board_row.get("Over Price"),
        board_row.get("Under Price"),
    )
    model_probability = over_prob if pick == "Over" else under_prob
    implied_probability = totals_market["over_raw"] if pick == "Over" else totals_market["under_raw"]
    no_vig_probability = totals_market["over_market_prob"] if pick == "Over" else totals_market["under_market_prob"]
    edge = _to_float(board_row.get("Over Edge %" if pick == "Over" else "Under Edge %"))
    ev = _to_float(board_row.get("Over EV" if pick == "Over" else "Under EV"))
    away_team = str(board_row.get("Away", "")).strip()
    home_team = str(board_row.get("Home", "")).strip()
    game_id, match_method = _match_game_id(away_team, home_team, game_date)

    return {
        "tracking_key": _build_tracking_key(snapshot_timestamp, away_team, home_team, "total"),
        "snapshot_group_id": snapshot_timestamp,
        "snapshot_timestamp": snapshot_timestamp,
        "game_date": game_date,
        "game_id": game_id,
        "game_match_method": match_method,
        "away_team": away_team,
        "home_team": home_team,
        "market_type": "total",
        "event_id": str(board_row.get("Event Id", "")).strip() or None,
        "bookmaker_key": str(board_row.get("Bookmaker Key", "")).strip() or None,
        "sport_key": str(board_row.get("Sport Key", "")).strip() or "baseball_mlb",
        "commence_time": str(board_row.get("Commence Time", "")).strip() or None,
        "sportsbook": str(board_row.get("Sportsbook", "")).strip() or None,
        "pick": pick,
        "model_win_probability": model_probability,
        "projected_total": projected_total,
        "locked_line": total_line,
        "locked_odds": locked_odds,
        "locked_implied_probability": implied_probability,
        "market_implied_probability": implied_probability,
        "market_no_vig_probability": no_vig_probability,
        "edge": edge,
        "ev": None if ev is None else ev / 100.0,
        "best_bet_flag": pick,
        "signal_strength": signal_strength,
        "is_actionable": 1 if is_actionable else 0,
        "tracking_mode": tracking_mode,
        "edge_bucket": _edge_bucket(edge),
        "closing_implied_probability": None,
        "closing_captured_at": None,
        "clv_value": None,
        "clv_direction": "Flat",
        "close_status": "Awaiting Close",
        "source": "manual",
    }


def _calculate_row_clv(row: dict[str, Any] | pd.Series) -> float | None:
    market_type = str(row.get("market_type", ""))
    pick = str(row.get("pick", ""))
    if market_type == "moneyline":
        clv_value, _ = calculate_side_clv_metrics(
            {
                "best_bet": pick,
                "away_team": row.get("away_team"),
                "home_team": row.get("home_team"),
                "open_away_ml": row.get("locked_odds") if pick == str(row.get("away_team")) else None,
                "open_home_ml": row.get("locked_odds") if pick == str(row.get("home_team")) else None,
                "close_away_ml": row.get("closing_odds") if pick == str(row.get("away_team")) else None,
                "close_home_ml": row.get("closing_odds") if pick == str(row.get("home_team")) else None,
            }
        )
        return clv_value

    clv_value, _ = calculate_total_clv_metrics(
        {
            "best_total_bet": pick,
            "open_total": row.get("locked_line"),
            "close_total": row.get("closing_line"),
            "open_over_price": row.get("locked_odds") if pick == "Over" else None,
            "open_under_price": row.get("locked_odds") if pick == "Under" else None,
            "close_over_price": row.get("closing_odds") if pick == "Over" else None,
            "close_under_price": row.get("closing_odds") if pick == "Under" else None,
        }
    )
    return clv_value


def _load_synced_performance_df() -> pd.DataFrame:
    return _load_performance_df()


def build_snapshot_records(
    board_rows: list[dict[str, str]],
    game_date: str | None,
    tracking_mode: str = "full_visible_board",
    snapshot_note: str | None = None,
) -> list[dict[str, Any]]:
    """Build paper-tracking rows from the visible board using the selected tracking mode."""
    if not board_rows or not game_date:
        return []

    tracking_mode = _normalize_tracking_mode(tracking_mode)
    snapshot_timestamp = _utc_now_iso()
    snapshot_note = str(snapshot_note or "").strip() or None
    records: list[dict[str, Any]] = []
    for row in board_rows:
        side_row = _build_side_snapshot_row(row, snapshot_timestamp, game_date, tracking_mode)
        if side_row is not None:
            side_row["snapshot_note"] = snapshot_note
            records.append(side_row)

        total_row = _build_total_snapshot_row(row, snapshot_timestamp, game_date, tracking_mode)
        if total_row is not None:
            total_row["snapshot_note"] = snapshot_note
            records.append(total_row)

    return records


def save_snapshot_records(
    board_rows: list[dict[str, str]],
    game_date: str | None,
    tracking_mode: str = "full_visible_board",
    snapshot_note: str | None = None,
) -> dict[str, int | str]:
    """Persist manual snapshot records into SQLite."""
    records = build_snapshot_records(board_rows, game_date, tracking_mode=tracking_mode, snapshot_note=snapshot_note)
    if not records:
        return {
            "saved_rows": 0,
            "actionable_rows": 0,
            "non_actionable_rows": 0,
            "tracking_mode": _normalize_tracking_mode(tracking_mode),
        }

    initialize_database()
    timestamp_now = _utc_now_iso()
    with get_connection() as connection:
        connection.executemany(
            f"""
            INSERT INTO {PERFORMANCE_TABLE} (
                tracking_key,
                snapshot_group_id,
                snapshot_timestamp,
                snapshot_note,
                game_date,
                game_id,
                game_match_method,
                away_team,
                home_team,
                market_type,
                event_id,
                bookmaker_key,
                sport_key,
                commence_time,
                sportsbook,
                pick,
                model_win_probability,
                projected_total,
                locked_line,
                locked_odds,
                locked_implied_probability,
                market_implied_probability,
                market_no_vig_probability,
                edge,
                ev,
                best_bet_flag,
                signal_strength,
                is_actionable,
                tracking_mode,
                edge_bucket,
                closing_implied_probability,
                closing_captured_at,
                clv_value,
                clv_direction,
                close_status,
                source,
                updated_at
            ) VALUES (
                :tracking_key,
                :snapshot_group_id,
                :snapshot_timestamp,
                :snapshot_note,
                :game_date,
                :game_id,
                :game_match_method,
                :away_team,
                :home_team,
                :market_type,
                :event_id,
                :bookmaker_key,
                :sport_key,
                :commence_time,
                :sportsbook,
                :pick,
                :model_win_probability,
                :projected_total,
                :locked_line,
                :locked_odds,
                :locked_implied_probability,
                :market_implied_probability,
                :market_no_vig_probability,
                :edge,
                :ev,
                :best_bet_flag,
                :signal_strength,
                :is_actionable,
                :tracking_mode,
                :edge_bucket,
                :closing_implied_probability,
                :closing_captured_at,
                :clv_value,
                :clv_direction,
                :close_status,
                :source,
                :updated_at
            )
            ON CONFLICT(tracking_key) DO UPDATE SET
                event_id = COALESCE(excluded.event_id, performance_bets.event_id),
                bookmaker_key = COALESCE(excluded.bookmaker_key, performance_bets.bookmaker_key),
                sport_key = COALESCE(excluded.sport_key, performance_bets.sport_key),
                commence_time = COALESCE(excluded.commence_time, performance_bets.commence_time),
                sportsbook = excluded.sportsbook,
                locked_line = excluded.locked_line,
                locked_odds = excluded.locked_odds,
                locked_implied_probability = excluded.locked_implied_probability,
                market_implied_probability = excluded.market_implied_probability,
                market_no_vig_probability = excluded.market_no_vig_probability,
                edge = excluded.edge,
                ev = excluded.ev,
                best_bet_flag = excluded.best_bet_flag,
                signal_strength = excluded.signal_strength,
                is_actionable = excluded.is_actionable,
                tracking_mode = excluded.tracking_mode,
                edge_bucket = excluded.edge_bucket,
                close_status = COALESCE(performance_bets.close_status, excluded.close_status),
                source = excluded.source,
                snapshot_note = COALESCE(excluded.snapshot_note, performance_bets.snapshot_note),
                updated_at = excluded.updated_at
            """,
            [
                {
                    **record,
                    "updated_at": timestamp_now,
                }
                for record in records
            ],
        )
        connection.commit()
    actionable_rows = sum(int(record.get("is_actionable", 0)) for record in records)
    saved_rows = len(records)
    return {
        "saved_rows": saved_rows,
        "actionable_rows": actionable_rows,
        "non_actionable_rows": saved_rows - actionable_rows,
        "tracking_mode": _normalize_tracking_mode(tracking_mode),
    }


def _load_performance_df() -> pd.DataFrame:
    initialize_database()
    with get_connection() as connection:
        return pd.read_sql_query(
            f"SELECT * FROM {PERFORMANCE_TABLE} ORDER BY snapshot_timestamp DESC, performance_bet_id DESC",
            connection,
        )


def _select_bookmaker(event_payload: dict[str, Any], tracked_row: dict[str, Any] | pd.Series) -> dict[str, Any] | None:
    bookmakers = event_payload.get("bookmakers", []) or []
    preferred_key = str(tracked_row.get("bookmaker_key") or "").strip()
    preferred_title = normalize_sportsbook_name(tracked_row.get("sportsbook"))

    if preferred_key:
        for bookmaker in bookmakers:
            if str(bookmaker.get("key") or "").strip() == preferred_key:
                return bookmaker

    if preferred_title:
        for bookmaker in bookmakers:
            if normalize_sportsbook_name(bookmaker.get("title")) == preferred_title:
                return bookmaker

    return choose_preferred_bookmaker(bookmakers)


def _row_is_open(row: dict[str, Any] | pd.Series) -> bool:
    result_value = str(row.get("result") or "").strip().lower()
    return result_value in {"", "open", "pending"}


def _row_capture_window(row: dict[str, Any] | pd.Series) -> str | None:
    if not _row_is_open(row):
        return None
    if row.get("closing_odds") not in (None, "") and not pd.isna(row.get("closing_odds")):
        return None
    if not str(row.get("event_id") or "").strip():
        return "missing_event_id"

    commence_dt = _parse_timestamp(row.get("commence_time"))
    if commence_dt is None:
        return None

    now_utc = datetime.now(timezone.utc)
    minutes_to_start = (commence_dt - now_utc).total_seconds() / 60.0
    if 0 <= minutes_to_start <= PRE_CLOSE_CAPTURE_WINDOW_MINUTES:
        return "pregame_fetch"
    if -RECENT_START_CAPTURE_WINDOW_MINUTES <= minutes_to_start < 0:
        return "recent_post_start_cache_only"
    return None


def _extract_close_from_payload(
    row: dict[str, Any] | pd.Series,
    event_payload: dict[str, Any],
) -> dict[str, Any] | None:
    bookmaker = _select_bookmaker(event_payload, row)
    if bookmaker is None:
        return None

    market_type = str(row.get("market_type") or "")
    pick = str(row.get("pick") or "")
    captured_at = _utc_now_iso()

    if market_type == "moneyline":
        market = parse_bookmaker_h2h_market(
            bookmaker,
            str(row.get("away_team") or ""),
            str(row.get("home_team") or ""),
        )
        if pick == str(row.get("away_team")):
            closing_odds = market.get("away_moneyline")
        elif pick == str(row.get("home_team")):
            closing_odds = market.get("home_moneyline")
        else:
            closing_odds = None
        if closing_odds is None:
            return None

        closing_implied_probability = american_odds_to_implied_prob(closing_odds)
        clv_value = _calculate_row_clv(
            {
                **dict(row),
                "closing_odds": closing_odds,
                "closing_line": None,
            }
        )
        return {
            "closing_line": None,
            "closing_odds": closing_odds,
            "closing_implied_probability": closing_implied_probability,
            "closing_captured_at": captured_at,
            "clv_value": clv_value,
            "clv": clv_value,
            "clv_direction": _clv_direction_label(clv_value),
            "close_status": "Captured Pregame Close",
            "sportsbook": bookmaker.get("title") or row.get("sportsbook"),
            "bookmaker_key": bookmaker.get("key") or row.get("bookmaker_key"),
        }

    totals_market = parse_bookmaker_totals_market(bookmaker)
    closing_line = totals_market.get("total_line")
    closing_odds = totals_market.get("over_price") if pick == "Over" else totals_market.get("under_price")
    if closing_line is None and closing_odds is None:
        return None

    closing_implied_probability = american_odds_to_implied_prob(closing_odds)
    clv_value = _calculate_row_clv(
        {
            **dict(row),
            "closing_line": closing_line,
            "closing_odds": closing_odds,
        }
    )
    return {
        "closing_line": closing_line,
        "closing_odds": closing_odds,
        "closing_implied_probability": closing_implied_probability,
        "closing_captured_at": captured_at,
        "clv_value": clv_value,
        "clv": clv_value,
        "clv_direction": _clv_direction_label(clv_value),
        "close_status": "Captured Pregame Close",
        "sportsbook": bookmaker.get("title") or row.get("sportsbook"),
        "bookmaker_key": bookmaker.get("key") or row.get("bookmaker_key"),
    }


def _latest_cached_pregame_event(row: dict[str, Any] | pd.Series) -> dict[str, Any] | None:
    event_id = str(row.get("event_id") or "").strip()
    if not event_id:
        return None
    market_scope = "h2h" if str(row.get("market_type")) == "moneyline" else "totals"
    cached_rows = read_cached_odds_rows([event_id], markets=market_scope)
    if not cached_rows:
        return None

    commence_dt = _parse_timestamp(row.get("commence_time"))
    if commence_dt is None:
        return None

    candidate_rows: list[dict[str, Any]] = []
    for cached_row in cached_rows:
        fetched_dt = _parse_timestamp(cached_row.get("fetched_at"))
        if fetched_dt is None or fetched_dt > commence_dt:
            continue
        candidate_rows.append(cached_row)

    if not candidate_rows:
        return None

    candidate_rows.sort(key=lambda item: _parse_timestamp(item.get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return dict(candidate_rows[0]["market_data"])


def capture_closing_lines(force_refresh: bool = False) -> dict[str, int]:
    performance_df = _load_performance_df()
    if performance_df.empty:
        return {
            "eligible_rows": 0,
            "updated_rows": 0,
            "skipped_rows": 0,
            "missing_event_ids": 0,
        }

    eligible_rows: list[tuple[pd.Series, str]] = []
    skipped_rows = 0
    missing_event_ids = 0
    for _, row in performance_df.iterrows():
        window = _row_capture_window(row)
        if window == "missing_event_id":
            missing_event_ids += 1
            continue
        if window is None:
            skipped_rows += 1
            continue
        eligible_rows.append((row, window))

    print(f"[Reflex Close Capture] eligible_rows={len(eligible_rows)}")
    updated_rows = 0
    with get_connection() as connection:
        for row, window in eligible_rows:
            event_id = str(row.get("event_id") or "").strip()
            market_scope = "h2h" if str(row.get("market_type")) == "moneyline" else "totals"
            print(f"[Reflex Close Capture] requesting event_id={event_id} | market={market_scope} | mode={window}")

            event_payload: dict[str, Any] | None = None
            if window == "pregame_fetch":
                event_payload, status = get_event_market_snapshot(
                    event_id,
                    market_scope,
                    force_refresh=force_refresh,
                )
                print(
                    "[Reflex Close Capture] api_status"
                    f" | event_id={event_id}"
                    f" | x-requests-remaining={status.get('requests_remaining')}"
                    f" | x-requests-used={status.get('requests_used')}"
                    f" | x-requests-last={status.get('requests_last')}"
                )
            else:
                event_payload = _latest_cached_pregame_event(row)
                print(f"[Reflex Close Capture] cache_only event_id={event_id} | found={event_payload is not None}")

            if event_payload is None:
                continue

            updates = _extract_close_from_payload(row, event_payload)
            if updates is None:
                continue

            connection.execute(
                f"""
                UPDATE {PERFORMANCE_TABLE}
                SET sportsbook = COALESCE(?, sportsbook),
                    bookmaker_key = COALESCE(?, bookmaker_key),
                    closing_line = COALESCE(?, closing_line),
                    closing_odds = COALESCE(?, closing_odds),
                    closing_implied_probability = COALESCE(?, closing_implied_probability),
                    closing_captured_at = COALESCE(?, closing_captured_at),
                    clv = COALESCE(?, clv),
                    clv_value = COALESCE(?, clv_value),
                    clv_direction = COALESCE(?, clv_direction),
                    close_status = COALESCE(?, close_status),
                    updated_at = ?
                WHERE performance_bet_id = ?
                """,
                (
                    updates.get("sportsbook"),
                    updates.get("bookmaker_key"),
                    updates.get("closing_line"),
                    updates.get("closing_odds"),
                    updates.get("closing_implied_probability"),
                    updates.get("closing_captured_at"),
                    updates.get("clv"),
                    updates.get("clv_value"),
                    updates.get("clv_direction"),
                    updates.get("close_status"),
                    _utc_now_iso(),
                    int(row["performance_bet_id"]),
                ),
            )
            updated_rows += 1
        connection.commit()

    print(f"[Reflex Close Capture] rows_successfully_updated={updated_rows}")
    return {
        "eligible_rows": len(eligible_rows),
        "updated_rows": updated_rows,
        "skipped_rows": skipped_rows,
        "missing_event_ids": missing_event_ids,
    }


def grade_performance_bets() -> dict[str, int]:
    """Grade all saved paper bets whose final scores are available."""
    _refresh_recent_final_games()
    relinked_rows = _relink_open_performance_bets()
    performance_df = _load_performance_df()
    if performance_df.empty:
        return {
            "eligible_rows": 0,
            "graded_rows": 0,
            "closing_line_updates": 0,
            "relinked_rows": relinked_rows,
        }

    close_capture_results = capture_closing_lines(force_refresh=False)
    closing_line_updates = int(close_capture_results.get("updated_rows", 0))
    initialize_database()
    query = f"""
        SELECT
            perf.*,
            games.home_score,
            games.away_score
        FROM {PERFORMANCE_TABLE} perf
        LEFT JOIN games ON perf.game_id = games.game_id
        WHERE perf.graded_at IS NULL
          AND games.home_score IS NOT NULL
          AND games.away_score IS NOT NULL
    """
    with get_connection() as connection:
        gradable_df = pd.read_sql_query(query, connection)

    if gradable_df.empty:
        return {
            "eligible_rows": 0,
            "graded_rows": 0,
            "closing_line_updates": closing_line_updates,
            "relinked_rows": relinked_rows,
        }

    graded_rows = 0
    graded_at = _utc_now_iso()
    with get_connection() as connection:
        for _, row in gradable_df.iterrows():
            market_type = str(row.get("market_type"))
            away_runs = float(row.get("away_score"))
            home_runs = float(row.get("home_score"))
            pick = str(row.get("pick"))
            locked_odds = row.get("locked_odds")
            result = "push"
            units = 0.0
            clv = _to_float(row.get("clv_value"))

            if market_type == "moneyline":
                if pick == str(row.get("away_team")):
                    win = away_runs > home_runs
                    loss = away_runs < home_runs
                else:
                    win = home_runs > away_runs
                    loss = home_runs < away_runs

                if win:
                    units_value = american_odds_profit(locked_odds)
                    if units_value is None:
                        continue
                    units = float(units_value)
                    result = "win"
                elif loss:
                    units = -1.0
                    result = "loss"

                if clv is None:
                    clv, _ = calculate_side_clv_metrics(
                        {
                            "best_bet": pick,
                            "away_team": row.get("away_team"),
                            "home_team": row.get("home_team"),
                            "open_away_ml": row.get("locked_odds") if pick == str(row.get("away_team")) else None,
                            "open_home_ml": row.get("locked_odds") if pick == str(row.get("home_team")) else None,
                            "close_away_ml": row.get("closing_odds") if pick == str(row.get("away_team")) else None,
                            "close_home_ml": row.get("closing_odds") if pick == str(row.get("home_team")) else None,
                        }
                    )
            else:
                final_total = away_runs + home_runs
                total_line = float(row.get("locked_line"))
                if pick == "Over":
                    win = final_total > total_line
                    loss = final_total < total_line
                else:
                    win = final_total < total_line
                    loss = final_total > total_line

                if win:
                    units_value = american_odds_profit(locked_odds)
                    if units_value is None:
                        continue
                    units = float(units_value)
                    result = "win"
                elif loss:
                    units = -1.0
                    result = "loss"

                if clv is None:
                    clv, _ = calculate_total_clv_metrics(
                        {
                            "best_total_bet": pick,
                            "open_total": row.get("locked_line"),
                            "close_total": row.get("closing_line"),
                            "open_over_price": row.get("locked_odds") if pick == "Over" else None,
                            "open_under_price": row.get("locked_odds") if pick == "Under" else None,
                            "close_over_price": row.get("closing_odds") if pick == "Over" else None,
                            "close_under_price": row.get("closing_odds") if pick == "Under" else None,
                        }
                    )

            connection.execute(
                f"""
                UPDATE {PERFORMANCE_TABLE}
                SET result = ?,
                    units = ?,
                    clv = ?,
                    clv_value = COALESCE(clv_value, ?),
                    clv_direction = COALESCE(clv_direction, ?),
                    closing_line = COALESCE(closing_line, ?),
                    closing_odds = COALESCE(closing_odds, ?),
                    final_away_runs = ?,
                    final_home_runs = ?,
                    graded_at = ?,
                    updated_at = ?
                WHERE performance_bet_id = ?
                """,
                (
                    result,
                    units,
                    clv,
                    clv,
                    _clv_direction_label(clv),
                    row.get("closing_line"),
                    row.get("closing_odds"),
                    away_runs,
                    home_runs,
                    graded_at,
                    graded_at,
                    int(row["performance_bet_id"]),
                ),
            )
            graded_rows += 1
        connection.commit()

    return {
        "eligible_rows": int(len(gradable_df)),
        "graded_rows": graded_rows,
        "closing_line_updates": closing_line_updates,
        "relinked_rows": relinked_rows,
    }


def delete_performance_rows(performance_bet_ids: list[int]) -> int:
    """Delete tracked performance rows by primary key."""
    valid_ids: list[int] = []
    for value in performance_bet_ids:
        try:
            valid_ids.append(int(value))
        except (TypeError, ValueError):
            continue

    valid_ids = sorted(set(valid_ids))
    if not valid_ids:
        return 0

    initialize_database()
    placeholders = ", ".join("?" for _ in valid_ids)
    with get_connection() as connection:
        cursor = connection.execute(
            f"DELETE FROM {PERFORMANCE_TABLE} WHERE performance_bet_id IN ({placeholders})",
            tuple(valid_ids),
        )
        connection.commit()
        return int(cursor.rowcount or 0)


def load_performance_rows() -> list[dict[str, str]]:
    df = _load_synced_performance_df()
    if df.empty:
        return []

    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        result_value = str(row.get("result", "")).strip().lower()
        result_label = {
            "win": "Win",
            "loss": "Loss",
            "push": "Push",
        }.get(result_value, "Open")
        rows.append(
            {
                "Date": str(row.get("game_date", "")),
                "Snapshot": _display_timestamp(row.get("snapshot_timestamp")),
                "Matchup": f"{row.get('away_team', '')} at {row.get('home_team', '')}",
                "Bet Type": "Side" if str(row.get("market_type")) == "moneyline" else "Total",
                "Pick": str(row.get("pick", "")),
                "Locked Odds": (
                    f"{int(row['locked_odds']):+d}" if not pd.isna(row.get("locked_odds")) else "-"
                ),
                "Model Edge": (
                    f"{float(row['edge']):+.1f}%" if not pd.isna(row.get("edge")) else "-"
                ),
                "EV": (
                    f"{float(row['ev']) * 100:+.1f}%" if not pd.isna(row.get("ev")) else "-"
                ),
                "Result": result_label,
                "Units": (
                    f"{float(row['units']):+.2f}" if not pd.isna(row.get("units")) else "-"
                ),
                "Signal": str(row.get("signal_strength", "")),
                "Actionability": "Actionable" if _coerce_actionable_flag(row.get("is_actionable")) else "Non-Actionable",
                "Tracking Mode": str(row.get("tracking_mode", "") or "full_visible_board").replace("_", " ").title(),
                "Note": str(row.get("snapshot_note", "") or ""),
                "Edge Bucket": str(row.get("edge_bucket", "")),
                "_performance_bet_id": str(int(row.get("performance_bet_id"))),
                "_market_type": str(row.get("market_type", "")),
                "_signal_strength": str(row.get("signal_strength", "")),
                "_is_actionable": str(_coerce_actionable_flag(row.get("is_actionable"))),
                "_tracking_mode": str(row.get("tracking_mode", "") or "full_visible_board"),
                "_edge_bucket": str(row.get("edge_bucket", "")),
                "_date": str(row.get("game_date", "")),
                "_snapshot_timestamp": str(row.get("snapshot_timestamp", "")),
                "_snapshot_note": str(row.get("snapshot_note", "") or ""),
                "_result_raw": result_value or "open",
                "_units_raw": "" if pd.isna(row.get("units")) else f"{float(row.get('units')):.4f}",
                "_event_id": str(row.get("event_id", "") or ""),
                "_bookmaker_key": str(row.get("bookmaker_key", "") or ""),
            }
        )
    return rows


def build_performance_summary() -> list[dict[str, str]]:
    df = _load_synced_performance_df()
    if df.empty:
        return [
            {"label": "Tracked Bets", "value": "0", "delta": "No paper bets locked yet"},
            {"label": "Win Rate", "value": "-", "delta": "Settled bets only"},
            {"label": "Units", "value": "-", "delta": "1u flat stake"},
            {"label": "ROI", "value": "-", "delta": "Units / settled bets"},
            {"label": "Open Bets", "value": "0", "delta": "Awaiting game results"},
            {"label": "Best Edge Bucket", "value": "-", "delta": "Highest ROI bucket"},
        ]

    settled_df = df[df["result"].isin(["win", "loss", "push"])].copy()
    decision_df = settled_df[settled_df["result"].isin(["win", "loss"])].copy()
    total_tracked = int(len(df))
    win_rate = "-"
    if not decision_df.empty:
        win_rate = f"{decision_df['result'].eq('win').mean() * 100:.1f}%"
    units = settled_df["units"].fillna(0).sum() if "units" in settled_df.columns else 0.0
    roi = "-"
    if not settled_df.empty:
        roi = f"{(units / len(settled_df)) * 100:.1f}%"
    open_bets = int(df["result"].fillna("").astype(str).str.strip().eq("").sum())

    best_edge_bucket = "-"
    if not settled_df.empty and "edge_bucket" in settled_df.columns:
        bucket_rows = []
        for bucket, bucket_df in settled_df.groupby("edge_bucket"):
            if bucket_df.empty:
                continue
            bucket_units = bucket_df["units"].fillna(0).sum()
            bucket_roi = bucket_units / len(bucket_df)
            bucket_rows.append((bucket_roi, bucket_units, str(bucket)))
        if bucket_rows:
            bucket_rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
            best_edge_bucket = bucket_rows[0][2]

    return [
        {"label": "Tracked Bets", "value": str(total_tracked), "delta": "Manual paper bets locked from the board"},
        {"label": "Win Rate", "value": win_rate, "delta": "Settled win/loss decisions only"},
        {"label": "Units", "value": f"{units:+.2f}", "delta": "Flat 1u staking"},
        {"label": "ROI", "value": roi, "delta": "Units earned per settled bet"},
        {"label": "Open Bets", "value": str(open_bets), "delta": "Awaiting game results"},
        {"label": "Best Edge Bucket", "value": best_edge_bucket, "delta": "Highest ROI edge range"},
    ]
