"""Starter command-line entry point for the MLB betting model project."""

from __future__ import annotations

import argparse

from app.config import get_project_paths
from app.db.schema import initialize_database


def build_parser() -> argparse.ArgumentParser:
    """Create a small CLI for beginner-friendly project commands."""
    parser = argparse.ArgumentParser(description="MLB betting model helper commands.")
    parser.add_argument(
        "command",
        nargs="?",
        default="info",
        choices=["info", "init-db"],
        help="Command to run. Use 'init-db' to create the SQLite database.",
    )
    return parser


def main() -> None:
    """Run a project command."""
    parser = build_parser()
    args = parser.parse_args()
    paths = get_project_paths()

    if args.command == "init-db":
        db_path = initialize_database()
        print(f"Database initialized at: {db_path}")
        return

    print("MLB Betting Model")
    print("Phase 2 database setup is ready.")
    print(f"Database path: {paths['db_path']}")
    print(f"Models folder: {paths['model_dir']}")
    print("Available commands: info, init-db")


if __name__ == "__main__":
    main()
