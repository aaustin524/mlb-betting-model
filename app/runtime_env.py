"""Environment and deployment helpers shared across local and cloud runs."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_DB_PATH = PROJECT_ROOT / "db" / "mlb_betting_model.sqlite"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "data" / "history"
SUPPORTED_DATABASE_SCHEMES = {"", "sqlite"}

# Load local development variables from the repo root when present.
load_dotenv(PROJECT_ROOT / ".env")


def get_env(name: str, default: str | None = None) -> str | None:
    """Read one environment variable and normalize blank strings to None."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    cleaned = raw_value.strip()
    return cleaned or default


def get_odds_api_key() -> str | None:
    """Return the Odds API key when configured."""
    return get_env("ODDS_API_KEY")


def get_database_url() -> str | None:
    """Return the optional DATABASE_URL override."""
    return get_env("DATABASE_URL")


def get_database_scheme() -> str:
    """Return the normalized database scheme for the current runtime."""
    database_url = get_database_url()
    if not database_url:
        return "sqlite"
    parsed = urlparse(database_url)
    return (parsed.scheme or "sqlite").lower()


def database_url_supported() -> bool:
    """Report whether the configured DATABASE_URL can be handled today."""
    return get_database_scheme() in SUPPORTED_DATABASE_SCHEMES


def resolve_database_path() -> Path:
    """Resolve the SQLite database path from environment variables."""
    database_url = get_database_url()
    if database_url:
        parsed = urlparse(database_url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in SUPPORTED_DATABASE_SCHEMES:
            raise ValueError(
                f"Unsupported DATABASE_URL scheme '{scheme}'. "
                "This deployment currently supports sqlite paths only."
            )
        if scheme == "sqlite":
            if parsed.netloc and parsed.netloc not in {"", "localhost"}:
                raw_path = f"/{parsed.netloc}{parsed.path}"
            else:
                raw_path = parsed.path
            if raw_path == ":memory:":
                return Path(":memory:")
            if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
                return (PROJECT_ROOT / unquote(raw_path.lstrip("/"))).expanduser().resolve()
            return Path(unquote(raw_path)).expanduser().resolve()

    db_path = get_env("MLB_MODEL_DB_PATH", str(DEFAULT_SQLITE_DB_PATH))
    return Path(str(db_path)).expanduser().resolve()


def get_history_dir() -> Path:
    """Return the history directory used by legacy snapshot helpers."""
    history_dir = get_env("MLB_MODEL_HISTORY_DIR", str(DEFAULT_HISTORY_DIR))
    return Path(str(history_dir)).expanduser().resolve()


def get_public_api_url() -> str | None:
    """Return an optional public backend URL for hosted browser traffic."""
    return get_env("API_URL") or get_env("REFLEX_API_URL") or get_env("REFLEX_PUBLIC_URL")


def get_deploy_url() -> str | None:
    """Return an optional public frontend URL for hosted deployment metadata."""
    return get_env("DEPLOY_URL") or get_env("REFLEX_DEPLOY_URL") or get_env("REFLEX_PUBLIC_URL")


def env_flag(name: str) -> bool:
    """Return True when the named environment variable is present."""
    return get_env(name) is not None
