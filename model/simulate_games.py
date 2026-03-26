import numpy as np

from project_config import DEFAULT_RUN_DISPERSION

_TEAM_COUNT = 2
_LOW_SCORE_ONE_TO_ZERO_PROB = 0.02
_LOW_SCORE_TWO_TO_ONE_PROB = 0.04
_HIGH_SCORE_EXTRA_RUN_PROB = 0.15


def _coerce_dispersion_k(dispersion_k=None, dispersion=None, k=None):
    """Resolve legacy dispersion aliases to one public ``dispersion_k`` value."""
    if dispersion_k is not None:
        return float(dispersion_k)
    if dispersion is not None:
        return float(dispersion)
    if k is not None:
        return float(k)
    return DEFAULT_RUN_DISPERSION


def _coerce_random_seed(random_seed=None, seed=None):
    """Resolve legacy seed aliases while keeping the newer public name."""
    if random_seed is not None:
        return random_seed
    return seed


def _validate_inputs(home_lambda, away_lambda, sims, dispersion_k):
    """Validate scalar simulation inputs before sampling runs."""
    if home_lambda < 0:
        raise ValueError("home_lambda must be non-negative")
    if away_lambda < 0:
        raise ValueError("away_lambda must be non-negative")
    if sims <= 0:
        raise ValueError("sims must be greater than 0")
    if dispersion_k <= 0:
        raise ValueError("dispersion_k must be greater than 0")


def _calibrate_run_distribution_tails(run_draws, rng):
    """
    Apply a light post-draw calibration to better match MLB scoring tails.

    Real MLB scoring tends to show slightly more 0-1 run games and slightly
    fatter 8+ run tails than a clean parametric draw produces. Rather than
    replace the Gamma-Poisson model, this nudges the simulated outcomes with a
    few small Bernoulli adjustments:

    - some 1-run outcomes are pushed down to 0
    - some 2-run outcomes are pushed down to 1
    - some 8+ run outcomes receive one extra run

    The probabilities are intentionally small so expected scoring stays close to
    the original lambda while the distribution looks more like historical MLB
    score frequencies.
    """
    calibrated_runs = run_draws.copy()

    one_run_mask = calibrated_runs == 1
    if np.any(one_run_mask):
        one_run_adjustments = rng.random(one_run_mask.sum()) < _LOW_SCORE_ONE_TO_ZERO_PROB
        calibrated_runs[one_run_mask] -= one_run_adjustments.astype(calibrated_runs.dtype)

    two_run_mask = calibrated_runs == 2
    if np.any(two_run_mask):
        two_run_adjustments = rng.random(two_run_mask.sum()) < _LOW_SCORE_TWO_TO_ONE_PROB
        calibrated_runs[two_run_mask] -= two_run_adjustments.astype(calibrated_runs.dtype)

    high_score_mask = calibrated_runs >= 8
    if np.any(high_score_mask):
        high_score_adjustments = rng.random(high_score_mask.sum()) < _HIGH_SCORE_EXTRA_RUN_PROB
        calibrated_runs[high_score_mask] += high_score_adjustments.astype(calibrated_runs.dtype)

    return calibrated_runs


def _draw_negative_binomial_runs(expected_runs, sims, dispersion, rng):
    """Draw one team's run totals with backward-compatible helper semantics."""
    expected_runs = float(expected_runs)
    sims = int(sims)
    dispersion = float(dispersion)
    if expected_runs < 0:
        raise ValueError("expected_runs must be non-negative")
    if sims <= 0:
        raise ValueError("sims must be greater than 0")
    if dispersion <= 0:
        raise ValueError("dispersion must be greater than 0")

    gamma_draws = rng.gamma(
        shape=dispersion,
        scale=1.0 / dispersion,
        size=sims,
    )
    run_draws = rng.poisson(gamma_draws * expected_runs)
    return _calibrate_run_distribution_tails(run_draws, rng)


def _simulate_run_arrays(home_lambda, away_lambda, sims, dispersion_k, rng):
    """
    Draw vectorized home and away run totals from a Gamma-Poisson mixture.

    The model is a Negative Binomial-style construction:

    - ``G ~ Gamma(k, scale=1/k)``
    - ``runs ~ Poisson(lambda * G)``

    Because the gamma multiplier has mean 1.0, expected runs remain equal to the
    original lambda. The extra gamma layer increases variance above the Poisson
    mean, which better matches baseball's overdispersed run scoring.
    """
    # Draw both teams in one batched call to reduce Python overhead and keep
    # the hottest simulation path entirely inside NumPy.
    gamma_draws = rng.gamma(
        shape=dispersion_k,
        scale=1.0 / dispersion_k,
        size=(_TEAM_COUNT, sims),
    )
    scoring_rates = gamma_draws * np.array([[home_lambda], [away_lambda]], dtype=np.float64)
    run_draws = rng.poisson(scoring_rates)
    calibrated_draws = _calibrate_run_distribution_tails(run_draws, rng)
    return calibrated_draws[0], calibrated_draws[1]


def simulate_game(
    lambda_home,
    lambda_away,
    sims=25000,
    dispersion_k=None,
    random_seed=None,
    dispersion=None,
    seed=None,
    k=None,
):
    """
    Simulate an MLB game with overdispersed scoring via a Gamma-Poisson mixture.

    This replaces a simple Poisson scoring model with a Negative Binomial-style
    hierarchy. For each simulated game, each team's Poisson scoring rate is
    multiplied by a gamma-distributed latent factor:

    - ``home_gamma ~ Gamma(k, scale=1/k)``
    - ``away_gamma ~ Gamma(k, scale=1/k)``
    - ``home_runs ~ Poisson(home_lambda * home_gamma)``
    - ``away_runs ~ Poisson(away_lambda * away_gamma)``

    This preserves the requested mean run environment while allowing variance to
    exceed the mean, which is more realistic for baseball scoring than a pure
    Poisson assumption.

    Parameters
    ----------
    lambda_home : float
        Expected runs for the home team.
    lambda_away : float
        Expected runs for the away team.
    sims : int, default 25000
        Number of Monte Carlo simulations to run.
    dispersion_k : float or None, default None
        Gamma shape parameter controlling overdispersion. Larger values move the
        model closer to Poisson; smaller values widen the scoring distribution.
        When omitted, the default repository value of 6.0 is used.
    random_seed : int or None, default None
        Optional random seed for reproducible simulation output.
    dispersion : float or None
        Backward-compatible alias for ``dispersion_k``.
    seed : int or None
        Backward-compatible alias for ``random_seed``.
    k : float or None
        Backward-compatible alias for ``dispersion_k``.

    Returns
    -------
    dict
        Simulation summary with win probabilities, tie probability, mean runs,
        and simulated run arrays for compatibility with downstream analysis.
    """
    home_lambda = float(lambda_home)
    away_lambda = float(lambda_away)
    sims = int(sims)
    dispersion_k = _coerce_dispersion_k(
        dispersion_k=dispersion_k,
        dispersion=dispersion,
        k=k,
    )
    random_seed = _coerce_random_seed(random_seed=random_seed, seed=seed)

    _validate_inputs(home_lambda, away_lambda, sims, dispersion_k)

    rng = np.random.default_rng(random_seed)
    home_runs, away_runs = _simulate_run_arrays(
        home_lambda=home_lambda,
        away_lambda=away_lambda,
        sims=sims,
        dispersion_k=dispersion_k,
        rng=rng,
    )

    # Compare once, then reuse the result for win/loss/tie counts.
    run_diff = home_runs - away_runs
    home_wins = int(np.count_nonzero(run_diff > 0))
    ties = int(np.count_nonzero(run_diff == 0))
    away_wins = sims - home_wins - ties

    # Summaries from sums avoid a second pass through NumPy's mean machinery.
    home_runs_mean = float(home_runs.sum(dtype=np.int64) / sims)
    away_runs_mean = float(away_runs.sum(dtype=np.int64) / sims)

    return {
        "home_win_prob": home_wins / sims,
        "away_win_prob": away_wins / sims,
        "tie_prob": ties / sims,
        "home_runs_mean": home_runs_mean,
        "away_runs_mean": away_runs_mean,
        "avg_home_runs": home_runs_mean,
        "avg_away_runs": away_runs_mean,
        "home_runs": home_runs,
        "away_runs": away_runs,
        "dispersion_k": dispersion_k,
        "dispersion": dispersion_k,
    }


def simulate_matchup(
    home_lambda,
    away_lambda,
    sims=25000,
    dispersion_k=None,
    random_seed=None,
    seed=None,
    dispersion=None,
    k=None,
):
    """
    Backward-compatible wrapper for the matchup simulator.

    Some modules import ``simulate_matchup()`` directly, so this function keeps
    that public entry point while delegating to the shared Gamma-Poisson engine.
    """
    return simulate_game(
        lambda_home=home_lambda,
        lambda_away=away_lambda,
        sims=sims,
        dispersion_k=dispersion_k,
        random_seed=random_seed,
        dispersion=dispersion,
        seed=seed,
        k=k,
    )
