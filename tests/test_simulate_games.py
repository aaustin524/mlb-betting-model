import numpy as np

from model.simulate_games import DEFAULT_RUN_DISPERSION, _draw_negative_binomial_runs, simulate_game


def test_negative_binomial_draws_have_more_variance_than_poisson():
    expected_runs = 4.6
    dispersion = 2.0
    sims = 200000
    rng = np.random.default_rng(12345)

    draws = _draw_negative_binomial_runs(
        expected_runs=expected_runs,
        sims=sims,
        dispersion=dispersion,
        rng=rng,
    )

    sample_mean = float(draws.mean())
    sample_variance = float(draws.var())
    poisson_variance = expected_runs

    assert abs(sample_mean - expected_runs) < 0.08
    assert sample_variance > poisson_variance + 1.0


def test_higher_dispersion_moves_distribution_toward_poisson():
    expected_runs = 4.2
    sims = 200000

    wide_rng = np.random.default_rng(2026)
    tight_rng = np.random.default_rng(2026)

    wide_draws = _draw_negative_binomial_runs(
        expected_runs=expected_runs,
        sims=sims,
        dispersion=2.0,
        rng=wide_rng,
    )
    tight_draws = _draw_negative_binomial_runs(
        expected_runs=expected_runs,
        sims=sims,
        dispersion=25.0,
        rng=tight_rng,
    )

    assert float(wide_draws.var()) > float(tight_draws.var())
    assert abs(float(tight_draws.var()) - expected_runs) < 1.0


def test_simulate_game_keeps_backward_compatible_k_alias():
    result = simulate_game(
        lambda_home=4.5,
        lambda_away=4.1,
        sims=5000,
        k=DEFAULT_RUN_DISPERSION,
        seed=7,
    )

    assert 0 <= result["home_win_prob"] <= 1
    assert 0 <= result["away_win_prob"] <= 1
    assert result["dispersion"] == DEFAULT_RUN_DISPERSION
