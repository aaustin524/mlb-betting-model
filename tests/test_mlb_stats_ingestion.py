from app.ingest.mlb_stats import (
    build_pitcher_day_update,
    build_team_day_update,
    calculate_fip,
    parse_innings_pitched,
)


def test_parse_innings_pitched_converts_baseball_notation() -> None:
    assert parse_innings_pitched("5.0") == 5.0
    assert parse_innings_pitched("5.1") == 5 + (1 / 3)
    assert parse_innings_pitched("7.2") == 7 + (2 / 3)


def test_calculate_fip_returns_none_for_zero_innings() -> None:
    assert calculate_fip(1, 2, 0, 3, 0.0) is None


def test_build_team_day_update_rolls_same_day_rows_together() -> None:
    first = build_team_day_update(
        None,
        team_id=110,
        game_date="2026-03-26",
        wins=1,
        losses=0,
        runs_scored=4.0,
        runs_allowed=2.0,
    )
    combined = build_team_day_update(
        first,
        team_id=110,
        game_date="2026-03-26",
        wins=2,
        losses=0,
        runs_scored=3.0,
        runs_allowed=1.0,
    )

    assert combined["wins"] == 2
    assert combined["losses"] == 0
    assert combined["runs_scored"] == 7.0
    assert combined["runs_allowed"] == 3.0


def test_build_pitcher_day_update_rolls_same_day_rows_together() -> None:
    starter_info = {
        "pitcher_id": 123,
        "innings_pitched": 5 + (1 / 3),
        "earned_runs": 2,
        "strikeouts": 7,
        "walks": 1,
        "home_runs": 1,
        "hit_batters": 0,
    }
    first = build_pitcher_day_update(None, starter_info, "2026-03-26")
    combined = build_pitcher_day_update(
        first,
        {
            **starter_info,
            "innings_pitched": 1.0,
            "earned_runs": 0,
            "strikeouts": 2,
            "walks": 0,
            "home_runs": 0,
            "hit_batters": 1,
        },
        "2026-03-26",
    )

    assert combined["innings_pitched"] == 6 + (1 / 3)
    assert combined["earned_runs"] == 2
    assert combined["strikeouts"] == 9
    assert combined["walks"] == 1
    assert combined["_home_runs"] == 1
    assert combined["_hit_batters"] == 1
