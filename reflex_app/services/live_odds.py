"""Quota-aware live odds retrieval and caching for the Reflex board."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from app.db.connection import get_connection
from app.db.schema import initialize_database
from app.runtime_env import get_odds_api_key
from app.services.board_data import calculate_no_vig_probs, probability_to_american_odds
from model.clv_tracker import (
    choose_preferred_bookmaker,
    parse_bookmaker_h2h_market,
    parse_bookmaker_totals_market,
)


SPORT_KEY = "baseball_mlb"
SPORT_EVENTS_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events"
SPORT_ODDS_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"
EVENT_ODDS_URL_TEMPLATE = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/events/{{event_id}}/odds"
DEFAULT_REGIONS = "us"
DEFAULT_ODDS_FORMAT = "american"
DEFAULT_BOARD_MARKETS = "h2h,totals"
DEFAULT_DETAIL_MARKETS = "totals"
DEFAULT_CACHE_TTL_MINUTES = 10
NEAR_START_CACHE_TTL_MINUTES = 3
NEAR_START_WINDOW_MINUTES = 60
LOW_CREDIT_THRESHOLD = 25
REQUEST_TIMEOUT = 20
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
TEAM_NAME_ALIASES = {
    "athletics": "oakland athletics",
}


def normalize_team_name(team_name: str | None) -> str:
    """Normalize team names so cached odds can match board rows."""
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

    normalized_value = " ".join(token for token in normalized.split() if token not in {"the"})
    return TEAM_NAME_ALIASES.get(normalized_value, normalized_value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _to_int(value: str | int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _response_headers_payload(response: requests.Response) -> dict[str, int | None]:
    return {
        "requests_remaining": _to_int(response.headers.get("x-requests-remaining")),
        "requests_used": _to_int(response.headers.get("x-requests-used")),
        "requests_last": _to_int(response.headers.get("x-requests-last")),
    }


def _event_local_date(event: dict[str, Any]) -> str | None:
    event_dt = _parse_timestamp(str(event.get("commence_time") or ""))
    if event_dt is None:
        return None
    return event_dt.astimezone(LOCAL_TIMEZONE).date().isoformat()


def discover_upcoming_events() -> list[dict[str, Any]]:
    """Use the free events endpoint to discover upcoming MLB events."""
    api_key = get_odds_api_key()
    if not api_key:
        print("[Reflex Odds] Event discovery skipped: missing ODDS_API_KEY.")
        return []

    try:
        response = requests.get(
            SPORT_EVENTS_URL,
            params={"apiKey": api_key},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[Reflex Odds] Event discovery failed: {exc}")
        return []

    try:
        payload = response.json()
    except ValueError:
        print("[Reflex Odds] Event discovery returned invalid JSON.")
        return []

    if not isinstance(payload, list):
        return []
    return payload


def build_market_consensus(bookmakers: list[dict[str, Any]], away_team: str, home_team: str) -> dict[str, Any]:
    """Average no-vig bookmaker probabilities into one consensus view."""
    valid_book_probabilities: list[dict[str, float]] = []
    valid_hold_values: list[float] = []

    for bookmaker in bookmakers or []:
        h2h_prices = parse_bookmaker_h2h_market(bookmaker, away_team, home_team)
        away_price = h2h_prices.get("away_moneyline")
        home_price = h2h_prices.get("home_moneyline")
        if away_price is None or home_price is None:
            continue

        _, _, away_no_vig, home_no_vig, vig = calculate_no_vig_probs(away_price, home_price)
        if away_no_vig is None or home_no_vig is None:
            continue

        valid_book_probabilities.append(
            {
                "away_no_vig": float(away_no_vig),
                "home_no_vig": float(home_no_vig),
            }
        )
        if vig is not None:
            valid_hold_values.append(float(vig))

    if not valid_book_probabilities:
        return {
            "away_consensus_prob": None,
            "home_consensus_prob": None,
            "consensus_hold_avg": None,
            "consensus_books_used": 0,
            "away_fair_ml": None,
            "home_fair_ml": None,
        }

    away_consensus_prob = sum(item["away_no_vig"] for item in valid_book_probabilities) / len(valid_book_probabilities)
    home_consensus_prob = sum(item["home_no_vig"] for item in valid_book_probabilities) / len(valid_book_probabilities)
    consensus_hold_avg = sum(valid_hold_values) / len(valid_hold_values) if valid_hold_values else None

    return {
        "away_consensus_prob": away_consensus_prob,
        "home_consensus_prob": home_consensus_prob,
        "consensus_hold_avg": consensus_hold_avg,
        "consensus_books_used": len(valid_book_probabilities),
        "away_fair_ml": probability_to_american_odds(away_consensus_prob),
        "home_fair_ml": probability_to_american_odds(home_consensus_prob),
    }


def get_cache_ttl(commence_time: str | None) -> timedelta:
    """Shorten TTL when a game is close to first pitch."""
    commence_dt = _parse_timestamp(commence_time)
    if commence_dt is None:
        return timedelta(minutes=DEFAULT_CACHE_TTL_MINUTES)

    if commence_dt - _utc_now() <= timedelta(minutes=NEAR_START_WINDOW_MINUTES):
        return timedelta(minutes=NEAR_START_CACHE_TTL_MINUTES)
    return timedelta(minutes=DEFAULT_CACHE_TTL_MINUTES)


def is_cache_fresh(fetched_at: str | None, commence_time: str | None) -> bool:
    """Return True when cached odds are still within the right TTL window."""
    fetched_dt = _parse_timestamp(fetched_at)
    if fetched_dt is None:
        return False
    return _utc_now() - fetched_dt <= get_cache_ttl(commence_time)


def read_cached_odds_rows(
    event_ids: list[str],
    markets: str,
    regions: str = DEFAULT_REGIONS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
) -> list[dict[str, Any]]:
    """Read cached odds rows for the requested events and market scope."""
    if not event_ids:
        return []

    initialize_database()
    placeholders = ", ".join("?" for _ in event_ids)
    query = f"""
        SELECT
            event_id,
            sport_key,
            regions,
            markets,
            odds_format,
            away_team,
            home_team,
            commence_time,
            fetched_at,
            market_data_json,
            requests_remaining,
            requests_used,
            requests_last,
            source
        FROM odds_api_cache
        WHERE event_id IN ({placeholders})
          AND sport_key = ?
          AND regions = ?
          AND markets = ?
          AND odds_format = ?
    """
    params: list[Any] = list(event_ids) + [SPORT_KEY, regions, markets, odds_format]
    with get_connection() as connection:
        rows = pd.read_sql_query(query, connection, params=params)

    if rows.empty:
        return []

    records = rows.to_dict("records")
    for record in records:
        record["market_data"] = json.loads(record.pop("market_data_json"))
    return records


def write_cached_odds_rows(
    events: list[dict[str, Any]],
    markets: str,
    headers: dict[str, int | None],
    regions: str = DEFAULT_REGIONS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
) -> None:
    """Persist odds response rows so the board can reuse them until they expire."""
    if not events:
        return

    initialize_database()
    fetched_at = _utc_now().isoformat()
    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO odds_api_cache (
                event_id,
                sport_key,
                regions,
                markets,
                odds_format,
                away_team,
                home_team,
                commence_time,
                fetched_at,
                market_data_json,
                requests_remaining,
                requests_used,
                requests_last,
                source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, regions, markets, odds_format) DO UPDATE SET
                away_team = excluded.away_team,
                home_team = excluded.home_team,
                commence_time = excluded.commence_time,
                fetched_at = excluded.fetched_at,
                market_data_json = excluded.market_data_json,
                requests_remaining = excluded.requests_remaining,
                requests_used = excluded.requests_used,
                requests_last = excluded.requests_last,
                source = excluded.source
            """,
            [
                (
                    str(event.get("id") or ""),
                    SPORT_KEY,
                    regions,
                    markets,
                    odds_format,
                    str(event.get("away_team") or ""),
                    str(event.get("home_team") or ""),
                    str(event.get("commence_time") or ""),
                    fetched_at,
                    json.dumps(event),
                    headers.get("requests_remaining"),
                    headers.get("requests_used"),
                    headers.get("requests_last"),
                    "LIVE API",
                )
                for event in events
                if event.get("id")
            ],
        )
        connection.commit()


def latest_quota_status() -> dict[str, Any]:
    """Return the most recent quota snapshot written to cache."""
    initialize_database()
    query = """
        SELECT
            fetched_at,
            requests_remaining,
            requests_used,
            requests_last
        FROM odds_api_cache
        WHERE requests_remaining IS NOT NULL
        ORDER BY fetched_at DESC
        LIMIT 1
    """
    with get_connection() as connection:
        row = connection.execute(query).fetchone()

    if row is None:
        return {
            "fetched_at": None,
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
        }

    return {
        "fetched_at": row[0],
        "requests_remaining": row[1],
        "requests_used": row[2],
        "requests_last": row[3],
    }


def auto_refresh_enabled() -> bool:
    """Disable automatic paid refreshes when the monthly balance gets tight."""
    remaining = latest_quota_status().get("requests_remaining")
    if remaining is None:
        return True
    return int(remaining) >= LOW_CREDIT_THRESHOLD


def filter_events_for_board(events: list[dict[str, Any]], matchups: pd.DataFrame) -> list[dict[str, Any]]:
    """Keep only free-discovery events that belong to the board slate."""
    if not events or matchups.empty:
        return []

    matchup_keys = {
        (
            normalize_team_name(str(row.get("away_team") or "")),
            normalize_team_name(str(row.get("home_team") or "")),
        )
        for _, row in matchups.iterrows()
    }
    slate_dates = {
        str(row.get("game_date"))[:10]
        for _, row in matchups.iterrows()
        if str(row.get("game_date") or "")
    }

    filtered_events: list[dict[str, Any]] = []
    for event in events:
        event_key = (
            normalize_team_name(str(event.get("away_team") or "")),
            normalize_team_name(str(event.get("home_team") or "")),
        )
        event_date = _event_local_date(event)
        if event_key in matchup_keys and (not slate_dates or event_date in slate_dates):
            filtered_events.append(event)
    return filtered_events


def _fetch_paid_sport_odds(
    markets: str,
    regions: str = DEFAULT_REGIONS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    """Fetch the paid board-wide odds endpoint once for the requested market scope."""
    api_key = get_odds_api_key()
    if not api_key:
        print("[Reflex Odds] Paid odds fetch skipped: missing ODDS_API_KEY.")
        return [], {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": "missing_odds_api_key",
        }

    try:
        response = requests.get(
            SPORT_ODDS_URL,
            params={
                "apiKey": api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            },
            timeout=REQUEST_TIMEOUT,
        )
        headers = _response_headers_payload(response)
        print(
            "[Reflex Odds] LIVE API paid request"
            f" | markets={markets}"
            f" | x-requests-remaining={headers['requests_remaining']}"
            f" | x-requests-used={headers['requests_used']}"
            f" | x-requests-last={headers['requests_last']}"
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print(f"[Reflex Odds] Paid odds fetch failed: {exc}")
        return [], {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": str(exc),
        }
    except ValueError:
        print("[Reflex Odds] Paid odds fetch returned invalid JSON.")
        return [], {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": "invalid_json",
        }

    if not isinstance(payload, list):
        return [], headers
    return payload, headers


def _fetch_paid_event_odds(
    event_id: str,
    markets: str,
    regions: str = DEFAULT_REGIONS,
    odds_format: str = DEFAULT_ODDS_FORMAT,
) -> tuple[dict[str, Any] | None, dict[str, int | None]]:
    """Fetch detailed odds for one event only, used by deeper matchup views."""
    api_key = get_odds_api_key()
    if not api_key:
        print("[Reflex Odds] Detailed event fetch skipped: missing ODDS_API_KEY.")
        return None, {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": "missing_odds_api_key",
        }

    try:
        response = requests.get(
            EVENT_ODDS_URL_TEMPLATE.format(event_id=event_id),
            params={
                "apiKey": api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            },
            timeout=REQUEST_TIMEOUT,
        )
        headers = _response_headers_payload(response)
        print(
            "[Reflex Odds] LIVE API detailed request"
            f" | event_id={event_id}"
            f" | markets={markets}"
            f" | x-requests-remaining={headers['requests_remaining']}"
            f" | x-requests-used={headers['requests_used']}"
            f" | x-requests-last={headers['requests_last']}"
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        print(f"[Reflex Odds] Detailed event fetch failed: {exc}")
        return None, {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": str(exc),
        }
    except ValueError:
        print("[Reflex Odds] Detailed event fetch returned invalid JSON.")
        return None, {
            "requests_remaining": None,
            "requests_used": None,
            "requests_last": None,
            "error_message": "invalid_json",
        }

    if not isinstance(payload, dict):
        return None, headers
    return payload, headers


def build_market_lookup(events: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Convert raw events into the board market shape expected by shared services."""
    market_lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for event in events:
        away_team = str(event.get("away_team") or "").strip()
        home_team = str(event.get("home_team") or "").strip()
        if not away_team or not home_team:
            continue

        bookmakers = event.get("bookmakers", [])
        selected_bookmaker = choose_preferred_bookmaker(bookmakers)
        h2h_market = parse_bookmaker_h2h_market(selected_bookmaker, away_team, home_team)
        totals_market = parse_bookmaker_totals_market(selected_bookmaker)
        market_lookup[(normalize_team_name(away_team), normalize_team_name(home_team))] = {
            **h2h_market,
            **totals_market,
            **build_market_consensus(bookmakers, away_team, home_team),
            "sportsbook": selected_bookmaker.get("title") if selected_bookmaker else None,
            "bookmaker_key": selected_bookmaker.get("key") if selected_bookmaker else None,
            "event_id": event.get("id"),
            "sport_key": event.get("sport_key") or SPORT_KEY,
            "commence_time": event.get("commence_time"),
            "fetched_at": event.get("fetched_at"),
        }

    return market_lookup


def get_board_h2h_odds(
    matchups: pd.DataFrame,
    force_refresh: bool = False,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any]]:
    """Return board h2h odds using cache first and live API only when necessary."""
    discovery_events = discover_upcoming_events()
    board_events = filter_events_for_board(discovery_events, matchups)
    event_ids = [str(event.get("id")) for event in board_events if event.get("id")]
    cached_rows = read_cached_odds_rows(event_ids, markets=DEFAULT_BOARD_MARKETS)
    cached_by_event = {
        str(row["event_id"]): row
        for row in cached_rows
    }

    fresh_cached_events: list[dict[str, Any]] = []
    stale_or_missing = False
    for event in board_events:
        event_id = str(event.get("id") or "")
        cached_row = cached_by_event.get(event_id)
        if cached_row is None:
            stale_or_missing = True
            continue

        if is_cache_fresh(cached_row.get("fetched_at"), cached_row.get("commence_time")) and not force_refresh:
            cached_event = dict(cached_row["market_data"])
            cached_event["fetched_at"] = cached_row.get("fetched_at")
            fresh_cached_events.append(cached_event)
        else:
            stale_or_missing = True

    if board_events and len(fresh_cached_events) == len(board_events) and not force_refresh:
        quota = latest_quota_status()
        print("[Reflex Odds] Board odds source: CACHE")
        return build_market_lookup(fresh_cached_events), {
            "source": "CACHE",
            "last_refreshed_at": max((event.get("fetched_at") for event in fresh_cached_events), default=None),
            "requests_remaining": quota.get("requests_remaining"),
            "requests_used": quota.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "auto_refresh_enabled": auto_refresh_enabled(),
            "manual_only": not auto_refresh_enabled(),
        }

    if not force_refresh and not auto_refresh_enabled():
        best_cached_events: list[dict[str, Any]] = []
        for cached_row in cached_rows:
            cached_event = dict(cached_row["market_data"])
            cached_event["fetched_at"] = cached_row.get("fetched_at")
            best_cached_events.append(cached_event)
        print("[Reflex Odds] Board odds source: CACHE")
        quota = latest_quota_status()
        return build_market_lookup(best_cached_events), {
            "source": "CACHE",
            "last_refreshed_at": max((event.get("fetched_at") for event in best_cached_events), default=None),
            "requests_remaining": quota.get("requests_remaining"),
            "requests_used": quota.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "auto_refresh_enabled": False,
            "manual_only": True,
        }

    if not board_events and cached_rows:
        best_cached_events = []
        for cached_row in cached_rows:
            cached_event = dict(cached_row["market_data"])
            cached_event["fetched_at"] = cached_row.get("fetched_at")
            best_cached_events.append(cached_event)
        print("[Reflex Odds] Board odds source: CACHE")
        quota = latest_quota_status()
        return build_market_lookup(best_cached_events), {
            "source": "CACHE",
            "last_refreshed_at": max((event.get("fetched_at") for event in best_cached_events), default=None),
            "requests_remaining": quota.get("requests_remaining"),
            "requests_used": quota.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "auto_refresh_enabled": auto_refresh_enabled(),
            "manual_only": not auto_refresh_enabled(),
        }

    live_payload, headers = _fetch_paid_sport_odds(DEFAULT_BOARD_MARKETS)
    live_board_events = filter_events_for_board(live_payload, matchups)
    live_source = "LIVE API" if live_payload else "CACHE"
    if live_board_events:
        write_cached_odds_rows(live_board_events, DEFAULT_BOARD_MARKETS, headers)

    if not live_board_events and cached_rows:
        fallback_cached_events = []
        for cached_row in cached_rows:
            cached_event = dict(cached_row["market_data"])
            cached_event["fetched_at"] = cached_row.get("fetched_at")
            fallback_cached_events.append(cached_event)
        print(
            "[Reflex Odds] Board odds source: CACHE"
            f" | live fetch unavailable={headers.get('error_message', 'no_live_board_events')}"
        )
        quota = latest_quota_status()
        return build_market_lookup(fallback_cached_events), {
            "source": "CACHE",
            "last_refreshed_at": max((event.get("fetched_at") for event in fallback_cached_events), default=None),
            "requests_remaining": quota.get("requests_remaining"),
            "requests_used": quota.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "auto_refresh_enabled": auto_refresh_enabled(),
            "manual_only": not auto_refresh_enabled(),
            "error_message": headers.get("error_message"),
        }

    print(
        f"[Reflex Odds] Board odds source: {live_source}"
        f" | credits_last={headers.get('requests_last') or 0}"
    )
    return build_market_lookup(live_board_events), {
        "source": live_source,
        "last_refreshed_at": _utc_now().isoformat() if live_payload else latest_quota_status().get("fetched_at"),
        "requests_remaining": headers.get("requests_remaining"),
        "requests_used": headers.get("requests_used"),
        "requests_last": headers.get("requests_last"),
        "credits_last": headers.get("requests_last") or 0,
        "auto_refresh_enabled": (
            headers.get("requests_remaining") is None
            or int(headers.get("requests_remaining")) >= LOW_CREDIT_THRESHOLD
        ),
        "manual_only": (
            headers.get("requests_remaining") is not None
            and int(headers.get("requests_remaining")) < LOW_CREDIT_THRESHOLD
        ),
        "had_stale_or_missing_cache": stale_or_missing,
        "error_message": headers.get("error_message"),
    }


def get_event_totals_odds(
    event_id: str,
    force_refresh: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Optionally fetch totals for one selected game only."""
    cached_rows = read_cached_odds_rows([event_id], markets=DEFAULT_DETAIL_MARKETS)
    if cached_rows and not force_refresh:
        cached_row = cached_rows[0]
        if is_cache_fresh(cached_row.get("fetched_at"), cached_row.get("commence_time")):
            print("[Reflex Odds] Detailed odds source: CACHE")
            return dict(cached_row["market_data"]), {
                "source": "CACHE",
                "last_refreshed_at": cached_row.get("fetched_at"),
                "requests_remaining": cached_row.get("requests_remaining"),
                "requests_used": cached_row.get("requests_used"),
                "requests_last": 0,
                "credits_last": 0,
                "manual_only": not auto_refresh_enabled(),
            }

    if not force_refresh and not auto_refresh_enabled() and cached_rows:
        cached_row = cached_rows[0]
        print("[Reflex Odds] Detailed odds source: CACHE")
        return dict(cached_row["market_data"]), {
            "source": "CACHE",
            "last_refreshed_at": cached_row.get("fetched_at"),
            "requests_remaining": cached_row.get("requests_remaining"),
            "requests_used": cached_row.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "manual_only": True,
        }

    live_event, headers = _fetch_paid_event_odds(event_id, DEFAULT_DETAIL_MARKETS)
    if live_event is not None:
        write_cached_odds_rows([live_event], DEFAULT_DETAIL_MARKETS, headers)
    elif cached_rows:
        cached_row = cached_rows[0]
        print(
            "[Reflex Odds] Detailed odds source: CACHE"
            f" | live fetch unavailable={headers.get('error_message', 'unknown')}"
        )
        return dict(cached_row["market_data"]), {
            "source": "CACHE",
            "last_refreshed_at": cached_row.get("fetched_at"),
            "requests_remaining": cached_row.get("requests_remaining"),
            "requests_used": cached_row.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "manual_only": not auto_refresh_enabled(),
            "error_message": headers.get("error_message"),
        }
    print(
        "[Reflex Odds] Detailed odds source: LIVE API"
        f" | credits_last={headers.get('requests_last') or 0}"
    )
    return live_event, {
        "source": "LIVE API",
        "last_refreshed_at": _utc_now().isoformat(),
        "requests_remaining": headers.get("requests_remaining"),
        "requests_used": headers.get("requests_used"),
        "requests_last": headers.get("requests_last"),
        "credits_last": headers.get("requests_last") or 0,
        "manual_only": (
            headers.get("requests_remaining") is not None
            and int(headers.get("requests_remaining")) < LOW_CREDIT_THRESHOLD
        ),
        "error_message": headers.get("error_message"),
    }


def get_event_market_snapshot(
    event_id: str,
    markets: str,
    force_refresh: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fetch one event's market payload with cache-first behavior."""
    cached_rows = read_cached_odds_rows([event_id], markets=markets)
    if cached_rows and not force_refresh:
        cached_row = cached_rows[0]
        if is_cache_fresh(cached_row.get("fetched_at"), cached_row.get("commence_time")):
            print(f"[Reflex Odds] Event market source: CACHE | event_id={event_id} | markets={markets}")
            return dict(cached_row["market_data"]), {
                "source": "CACHE",
                "last_refreshed_at": cached_row.get("fetched_at"),
                "requests_remaining": cached_row.get("requests_remaining"),
                "requests_used": cached_row.get("requests_used"),
                "requests_last": 0,
                "credits_last": 0,
                "manual_only": not auto_refresh_enabled(),
                "error_message": "",
            }

    live_event, headers = _fetch_paid_event_odds(event_id, markets)
    if live_event is not None:
        write_cached_odds_rows([live_event], markets, headers)
        print(
            "[Reflex Odds] Event market source: LIVE API"
            f" | event_id={event_id}"
            f" | markets={markets}"
            f" | credits_last={headers.get('requests_last') or 0}"
        )
        return live_event, {
            "source": "LIVE API",
            "last_refreshed_at": _utc_now().isoformat(),
            "requests_remaining": headers.get("requests_remaining"),
            "requests_used": headers.get("requests_used"),
            "requests_last": headers.get("requests_last"),
            "credits_last": headers.get("requests_last") or 0,
            "manual_only": (
                headers.get("requests_remaining") is not None
                and int(headers.get("requests_remaining")) < LOW_CREDIT_THRESHOLD
            ),
            "error_message": headers.get("error_message"),
        }

    if cached_rows:
        cached_row = cached_rows[0]
        print(
            "[Reflex Odds] Event market source: CACHE"
            f" | event_id={event_id}"
            f" | markets={markets}"
            f" | live fetch unavailable={headers.get('error_message', 'unknown')}"
        )
        return dict(cached_row["market_data"]), {
            "source": "CACHE",
            "last_refreshed_at": cached_row.get("fetched_at"),
            "requests_remaining": cached_row.get("requests_remaining"),
            "requests_used": cached_row.get("requests_used"),
            "requests_last": 0,
            "credits_last": 0,
            "manual_only": not auto_refresh_enabled(),
            "error_message": headers.get("error_message"),
        }

    return None, {
        "source": "CACHE",
        "last_refreshed_at": None,
        "requests_remaining": headers.get("requests_remaining"),
        "requests_used": headers.get("requests_used"),
        "requests_last": headers.get("requests_last"),
        "credits_last": headers.get("requests_last") or 0,
        "manual_only": not auto_refresh_enabled(),
        "error_message": headers.get("error_message"),
    }


def get_matchup_totals_detail(
    away_team: str,
    home_team: str,
    slate_date: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch or reuse totals detail for one selected matchup only."""
    discovery_events = discover_upcoming_events()
    target_key = (normalize_team_name(away_team), normalize_team_name(home_team))

    matching_event: dict[str, Any] | None = None
    for event in discovery_events:
        event_key = (
            normalize_team_name(str(event.get("away_team") or "")),
            normalize_team_name(str(event.get("home_team") or "")),
        )
        if event_key != target_key:
            continue
        event_date = _event_local_date(event)
        if slate_date and event_date != slate_date:
            continue
        matching_event = event
        break

    if matching_event is None:
        return {
            "available": False,
            "headline": "Totals market unavailable",
            "subheadline": "No matching live event was found for this matchup.",
            "market_line": "-",
            "over_price": "-",
            "under_price": "-",
            "source": "CACHE",
            "last_refreshed_at": "Not refreshed yet",
            "quota_note": "No event match found.",
        }

    event_id = str(matching_event.get("id") or "")
    if not event_id:
        return {
            "available": False,
            "headline": "Totals market unavailable",
            "subheadline": "The selected game did not include a valid event id.",
            "market_line": "-",
            "over_price": "-",
            "under_price": "-",
            "source": "CACHE",
            "last_refreshed_at": "Not refreshed yet",
            "quota_note": "No event id available.",
        }

    event_payload, status = get_event_totals_odds(event_id, force_refresh=force_refresh)
    if not event_payload:
        return {
            "available": False,
            "headline": "Totals market unavailable",
            "subheadline": "Detailed totals pricing has not been cached yet and no live response was returned.",
            "market_line": "-",
            "over_price": "-",
            "under_price": "-",
            "source": str(status.get("source", "CACHE")),
            "last_refreshed_at": str(status.get("last_refreshed_at", "Not refreshed yet")),
            "quota_note": (
                "Live totals are unavailable right now. Showing cached or empty detail."
                if status.get("error_message")
                else (
                    f"Last paid request cost {status.get('credits_last', 0)} credits."
                    if status.get("credits_last") not in (None, "")
                    else "Quota updates after paid requests."
                )
            ),
        }

    bookmakers = event_payload.get("bookmakers", [])
    selected_bookmaker = choose_preferred_bookmaker(bookmakers)
    totals_market = parse_bookmaker_totals_market(selected_bookmaker)
    market_line = totals_market.get("total_line")
    over_price = totals_market.get("over_price")
    under_price = totals_market.get("under_price")
    source = str(status.get("source", "CACHE"))
    last_refreshed_at = str(status.get("last_refreshed_at", "Not refreshed yet"))
    return {
        "available": market_line is not None,
        "headline": "Totals market",
        "subheadline": (
            f"{selected_bookmaker.get('title')} pricing for {away_team} at {home_team}."
            if selected_bookmaker
            else f"Detailed pricing for {away_team} at {home_team}."
        ),
        "market_line": "-" if market_line is None else f"{float(market_line):.1f}",
        "over_price": "-" if over_price is None else f"{int(over_price):+d}",
        "under_price": "-" if under_price is None else f"{int(under_price):+d}",
        "source": source,
        "last_refreshed_at": last_refreshed_at,
        "quota_note": (
            f"Source: {source} | last paid request cost {status.get('credits_last', 0)} credits."
            if str(status.get("credits_last", "")) != ""
            else f"Source: {source}"
        ),
    }
