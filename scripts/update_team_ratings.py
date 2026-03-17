from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from project_config import DB_PATH
from model.rolling_team_ratings import (
    DEFAULT_BASELINE_WEIGHT,
    DEFAULT_BULLPEN_LOOKBACK_GAMES,
    DEFAULT_OFFENSE_LOOKBACK_GAMES,
    DEFAULT_RECENT_WEIGHT,
    update_team_ratings_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh data/teams.csv with blended rolling team ratings."
    )
    parser.add_argument(
        "--baseline-path",
        default="data/teams.csv",
        help="Existing baseline team ratings CSV.",
    )
    parser.add_argument(
        "--output-path",
        default="data/teams.csv",
        help="Where to write the refreshed team ratings CSV.",
    )
    parser.add_argument(
        "--db-path",
        default=str(DB_PATH),
        help="SQLite database path with completed game history.",
    )
    parser.add_argument(
        "--baseline-weight",
        type=float,
        default=DEFAULT_BASELINE_WEIGHT,
        help="Weight on baseline ratings.",
    )
    parser.add_argument(
        "--recent-weight",
        type=float,
        default=DEFAULT_RECENT_WEIGHT,
        help="Weight on recent form.",
    )
    parser.add_argument(
        "--offense-lookback-games",
        type=int,
        default=DEFAULT_OFFENSE_LOOKBACK_GAMES,
        help="Recent games used for rolling offense.",
    )
    parser.add_argument(
        "--bullpen-lookback-games",
        type=int,
        default=DEFAULT_BULLPEN_LOOKBACK_GAMES,
        help="Recent games used for rolling bullpen form.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    updated_df = update_team_ratings_file(
        baseline_path=args.baseline_path,
        output_path=args.output_path,
        db_path=args.db_path,
        baseline_weight=args.baseline_weight,
        recent_weight=args.recent_weight,
        offense_lookback_games=args.offense_lookback_games,
        bullpen_lookback_games=args.bullpen_lookback_games,
    )

    print(f"Updated {len(updated_df)} team ratings rows at {Path(args.output_path).resolve()}")


if __name__ == "__main__":
    main()
