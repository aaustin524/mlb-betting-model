"""Starter entry point for the MLB betting model project."""

from app.config import get_project_paths


def main() -> None:
    """Print a simple startup message for Phase 1."""
    paths = get_project_paths()

    print("MLB Betting Model")
    print("Phase 1 project setup is ready.")
    print(f"Database path: {paths['db_path']}")
    print(f"Models folder: {paths['model_dir']}")


if __name__ == "__main__":
    main()
