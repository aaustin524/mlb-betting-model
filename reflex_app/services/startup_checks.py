"""Deployment-friendly startup checks for the Reflex app."""

from __future__ import annotations

from importlib import metadata

from app.db.connection import get_connection
from app.db.schema import initialize_database
from app.runtime_env import (
    database_url_supported,
    env_flag,
    get_database_scheme,
    get_database_url,
    get_history_dir,
    resolve_database_path,
)


MIN_REFLEX_VERSION = (0, 6, 6)
_HAS_RUN = False


def _version_tuple(version_text: str) -> tuple[int, ...]:
    digits: list[int] = []
    current = ""
    for character in version_text:
        if character.isdigit():
            current += character
            continue
        if current:
            digits.append(int(current))
            current = ""
        if len(digits) >= 3:
            break
    if current and len(digits) < 3:
        digits.append(int(current))
    while len(digits) < 3:
        digits.append(0)
    return tuple(digits[:3])


def run_startup_checks() -> None:
    """Run one-time startup checks and log concise readiness output."""
    global _HAS_RUN
    if _HAS_RUN:
        return

    reflex_version = metadata.version("reflex")
    if _version_tuple(reflex_version) < MIN_REFLEX_VERSION:
        raise RuntimeError(
            f"Reflex {reflex_version} is below the required minimum version 0.6.6."
        )

    database_scheme = get_database_scheme()
    if not database_url_supported():
        raise RuntimeError(
            "Unsupported DATABASE_URL scheme configured. "
            "This deployment currently supports sqlite paths only."
        )

    database_url_present = env_flag("DATABASE_URL")
    db_path = resolve_database_path()
    history_dir = get_history_dir()

    initialize_database()
    with get_connection() as connection:
        connection.execute("SELECT 1").fetchone()

    print(f"[Startup] Reflex version OK: {reflex_version}")
    print(
        "[Startup] Secrets"
        f" | ODDS_API_KEY={'present' if env_flag('ODDS_API_KEY') else 'missing'}"
        f" | DATABASE_URL={'present' if database_url_present else 'missing'}"
    )
    if database_url_present:
        print(
            "[Startup] Database config"
            f" | scheme={database_scheme}"
            f" | source=DATABASE_URL"
        )
    else:
        print(
            "[Startup] Database config"
            f" | scheme={database_scheme}"
            f" | path={db_path}"
        )
    print(f"[Startup] History directory ready: {history_dir}")
    print("[Startup] Database connection OK")
    print("[Startup] Key services initialized cleanly")
    _HAS_RUN = True
