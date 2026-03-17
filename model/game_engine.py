import hashlib
import pandas as pd

from model.bullpen_usage import estimate_bullpen_fatigue, load_recent_bullpen_usage
from model.park_factors import get_park_factor, load_park_factors
from model.pitcher_adjustments import get_pitcher_adjustment
from model.run_environment import get_run_environment_factor
from model.run_expectancy import calculate_expected_runs
from model.simulate_games import simulate_game
from model.weather import get_weather_adjustment
from model.weather_api import load_stadium_locations, get_weather_for_team
from project_config import (
    BASELINE_STARTER_INNINGS,
    DEFAULT_RUN_DISPERSION,
    MAX_STARTER_INNINGS,
    MIN_STARTER_INNINGS,
    REGULATION_INNINGS,
    STARTER_INNINGS_SLOPE,
)


def _build_simulation_seed(
    away_team,
    home_team,
    away_starter_rating,
    home_starter_rating,
    away_pitcher_throws,
    home_pitcher_throws,
    away_bullpen_fatigue,
    home_bullpen_fatigue,
    away_lineup_adjustment,
    home_lineup_adjustment,
    temperature_f,
    wind_factor,
    sims,
    run_dispersion,
):
    seed_input = (
        away_team,
        home_team,
        away_starter_rating,
        home_starter_rating,
        away_pitcher_throws,
        home_pitcher_throws,
        away_bullpen_fatigue,
        home_bullpen_fatigue,
        away_lineup_adjustment,
        home_lineup_adjustment,
        temperature_f,
        wind_factor,
        sims,
        run_dispersion,
    )
    seed_text = "|".join(str(value) for value in seed_input)
    seed_hash = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(seed_hash[:8], 16)


def _project_starter_innings(starter_rating):
    """
    Estimate expected starter innings from pitcher quality.

    The model uses starter rating as the main driver. Lower ratings correspond
    to better run prevention, so stronger starters are projected to work deeper
    into games. A simple linear mapping keeps the behavior deterministic and
    easy to reason about:

    - elite starters around 0.80 to 0.90 project near 6.0 to 6.5 innings
    - average starters around 1.00 project near 5.5 innings
    - weaker starters around 1.10 to 1.20 project near 4.5 to 5.0 innings
    """
    projected_ip = BASELINE_STARTER_INNINGS + ((1.0 - float(starter_rating)) * STARTER_INNINGS_SLOPE)
    return max(MIN_STARTER_INNINGS, min(MAX_STARTER_INNINGS, projected_ip))


def _project_bullpen_innings(starter_innings):
    """
    Allocate remaining regulation innings to the bullpen.

    Bullpen innings are the remainder after the projected starter workload and
    are bounded at zero so the relief share cannot become negative.
    """
    return max(0.0, REGULATION_INNINGS - float(starter_innings))


def _blend_run_prevention(starter_factor, bullpen_factor, starter_innings, bullpen_innings):
    """
    Blend starter and bullpen prevention using inning-weighted shares.

    This makes the starter influence only the innings he is expected to pitch,
    while the bullpen controls the remaining innings. The resulting prevention
    factor stays on the same scale as the existing team pitching inputs.
    """
    return (
        (float(starter_factor) * (float(starter_innings) / REGULATION_INNINGS))
        + (float(bullpen_factor) * (float(bullpen_innings) / REGULATION_INNINGS))
    )


def simulate_matchup(
    home_team,
    away_team,
    teams,
    home_starter_rating=1.00,
    away_starter_rating=1.00,
    away_pitcher_throws=None,
    home_pitcher_throws=None,
    away_bullpen_fatigue=None,
    home_bullpen_fatigue=None,
    home_lineup_adjustment=1.00,
    away_lineup_adjustment=1.00,
    temperature_f=None,
    wind_factor=None,
    sims=25000,
    run_dispersion=DEFAULT_RUN_DISPERSION,
    data_mode="local",
):
    """
    Simulate a single MLB matchup and return expected runs and win probabilities.

    Parameters
    ----------
    home_team : str
    away_team : str
    teams : pandas.DataFrame
        Team ratings dataframe indexed by team name.
    home_starter_rating : float
    away_starter_rating : float
    home_lineup_adjustment : float
    away_lineup_adjustment : float
    temperature_f : float or None
        Manual weather override. If None, use automated/default weather.
    wind_factor : float or None
        Manual weather override. If None, use automated/default weather.
    sims : int
    run_dispersion : float
        Negative Binomial size parameter used in the run simulation.
        Run variance is approximately mu + mu^2 / run_dispersion.
        Larger values approach Poisson variance; smaller values create wider outcomes.
    data_mode : str
        "local" or "live"
    """

    # Load supporting data
    park_df = load_park_factors()
    stadium_df = load_stadium_locations(data_mode=data_mode)
    bullpen_usage_df = load_recent_bullpen_usage()

    # Select the correct offensive split based on the opposing starter hand.
    home_vs_rhp = float(teams.loc[home_team, "offense_vs_rhp"])
    home_vs_lhp = float(teams.loc[home_team, "offense_vs_lhp"])
    away_vs_rhp = float(teams.loc[away_team, "offense_vs_rhp"])
    away_vs_lhp = float(teams.loc[away_team, "offense_vs_lhp"])

    if away_pitcher_throws == "R":
        selected_home_offense = home_vs_rhp
    elif away_pitcher_throws == "L":
        selected_home_offense = home_vs_lhp
    else:
        selected_home_offense = (home_vs_rhp + home_vs_lhp) / 2

    if home_pitcher_throws == "R":
        selected_away_offense = away_vs_rhp
    elif home_pitcher_throws == "L":
        selected_away_offense = away_vs_lhp
    else:
        selected_away_offense = (away_vs_rhp + away_vs_lhp) / 2

    adjusted_home_offense = selected_home_offense * home_lineup_adjustment
    adjusted_away_offense = selected_away_offense * away_lineup_adjustment

    # Bullpen inputs
    home_bullpen_rating = float(teams.loc[home_team, "bullpen"])
    away_bullpen_rating = float(teams.loc[away_team, "bullpen"])

    if away_bullpen_fatigue is None:
        away_bullpen_fatigue = estimate_bullpen_fatigue(away_team, bullpen_usage_df)

    if home_bullpen_fatigue is None:
        home_bullpen_fatigue = estimate_bullpen_fatigue(home_team, bullpen_usage_df)

    adjusted_home_bullpen = home_bullpen_rating + home_bullpen_fatigue
    adjusted_away_bullpen = away_bullpen_rating + away_bullpen_fatigue

    # Starter inputs
    home_starter_adjustment = get_pitcher_adjustment(home_starter_rating)
    away_starter_adjustment = get_pitcher_adjustment(away_starter_rating)

    # Project each starter's workload, then allocate the remaining innings to
    # the bullpen. Better starters are expected to pitch deeper into games,
    # which increases their share of run prevention.
    home_starter_ip = _project_starter_innings(home_starter_rating)
    away_starter_ip = _project_starter_innings(away_starter_rating)
    home_bullpen_ip = _project_bullpen_innings(home_starter_ip)
    away_bullpen_ip = _project_bullpen_innings(away_starter_ip)

    # Blend starter and bullpen prevention using their projected inning shares.
    # The home team's defense faces away hitters, and the away team's defense
    # faces home hitters, so each team gets its own weighted prevention factor.
    adjusted_home_pitching = _blend_run_prevention(
        starter_factor=home_starter_adjustment,
        bullpen_factor=adjusted_home_bullpen,
        starter_innings=home_starter_ip,
        bullpen_innings=home_bullpen_ip,
    )
    adjusted_away_pitching = _blend_run_prevention(
        starter_factor=away_starter_adjustment,
        bullpen_factor=adjusted_away_bullpen,
        starter_innings=away_starter_ip,
        bullpen_innings=away_bullpen_ip,
    )

    # Base expected runs
    expected_runs = calculate_expected_runs(
        home_offense=adjusted_home_offense,
        away_offense=adjusted_away_offense,
        home_pitching=adjusted_home_pitching,
        away_pitching=adjusted_away_pitching,
    )

    # Park factor
    park_factor = get_park_factor(home_team, park_df)
    home_lambda = expected_runs["home_lambda"] * park_factor
    away_lambda = expected_runs["away_lambda"] * park_factor

    # Automated/default weather by home team
    weather_data = get_weather_for_team(home_team, stadium_df, data_mode=data_mode)

    api_temperature_f = weather_data["temperature_f"]
    api_wind_factor = weather_data["wind_factor"]
    weather_source = weather_data["weather_source"]

    # Manual overrides if provided
    final_temperature_f = temperature_f if temperature_f is not None else api_temperature_f
    final_wind_factor = wind_factor if wind_factor is not None else api_wind_factor

    # Weather multiplier
    weather_multiplier = get_weather_adjustment(final_temperature_f, final_wind_factor)
    home_lambda = round(home_lambda * weather_multiplier, 3)
    away_lambda = round(away_lambda * weather_multiplier, 3)

    # League scoring climate drifts over time, so apply a small recent-environment
    # calibration after park and weather adjustments. This keeps the factor
    # lightweight and blended toward 1.00 instead of acting like a full re-fit.
    run_environment_factor = get_run_environment_factor()
    home_lambda = round(home_lambda * run_environment_factor, 3)
    away_lambda = round(away_lambda * run_environment_factor, 3)

    seed = _build_simulation_seed(
        away_team=away_team,
        home_team=home_team,
        away_starter_rating=away_starter_rating,
        home_starter_rating=home_starter_rating,
        away_pitcher_throws=away_pitcher_throws,
        home_pitcher_throws=home_pitcher_throws,
        away_bullpen_fatigue=away_bullpen_fatigue,
        home_bullpen_fatigue=home_bullpen_fatigue,
        away_lineup_adjustment=away_lineup_adjustment,
        home_lineup_adjustment=home_lineup_adjustment,
        temperature_f=final_temperature_f,
        wind_factor=final_wind_factor,
        sims=sims,
        run_dispersion=run_dispersion,
    )

    # Simulate game
    simulation_results = simulate_game(
        home_lambda,
        away_lambda,
        sims=sims,
        dispersion=run_dispersion,
        seed=seed,
    )

    # If simulate_game still returns tie_prob, fold it into away side for display
    home_win_prob = simulation_results["home_win_prob"]
    away_win_prob = simulation_results["away_win_prob"] + simulation_results.get("tie_prob", 0)

    return {
        "away_team": away_team,
        "home_team": home_team,
        "away_lambda": away_lambda,
        "home_lambda": home_lambda,
        "away_win_prob": away_win_prob,
        "home_win_prob": home_win_prob,
        "selected_away_offense": selected_away_offense,
        "selected_home_offense": selected_home_offense,
        "adjusted_away_offense": adjusted_away_offense,
        "adjusted_home_offense": adjusted_home_offense,
        "adjusted_away_pitching": adjusted_away_pitching,
        "adjusted_home_pitching": adjusted_home_pitching,
        "away_bullpen_rating": away_bullpen_rating,
        "home_bullpen_rating": home_bullpen_rating,
        "adjusted_away_bullpen": adjusted_away_bullpen,
        "adjusted_home_bullpen": adjusted_home_bullpen,
        "away_starter_ip": round(away_starter_ip, 2),
        "home_starter_ip": round(home_starter_ip, 2),
        "away_bullpen_ip": round(away_bullpen_ip, 2),
        "home_bullpen_ip": round(home_bullpen_ip, 2),
        "away_bullpen_fatigue": away_bullpen_fatigue,
        "home_bullpen_fatigue": home_bullpen_fatigue,
        "away_pitcher_throws": away_pitcher_throws,
        "home_pitcher_throws": home_pitcher_throws,
        "park_factor": park_factor,
        "weather_multiplier": weather_multiplier,
        "run_environment_factor": run_environment_factor,
        "temperature_f": final_temperature_f,
        "wind_factor": final_wind_factor,
        "weather_source": weather_source,
        "run_dispersion": run_dispersion,
    }
