"""Example of parallel Monte Carlo simulation performance - multi-threaded numpy vs rayon-parallel inline rust"""

import math
import os
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Annotated

import numpy as np

from xenoform_rs import rust, rust_dependency

# option parameters: spot, strike, risk-free rate, volatility, expiry (years)
S0, K, R, SIGMA, T = 100.0, 105.0, 0.02, 0.25, 1.0
N_STEPS = 252
SEED = 19937
N_THREADS = os.cpu_count() or 1


def _payoff_sum_np(
    s0: float, k: float, r: float, sigma: float, t: float, n_steps: int, n_paths: int, rng: np.random.Generator
) -> float:
    """Sum of Asian call payoffs over n_paths simulated paths.

    Operations are in-place to bound peak memory at one (n_paths, n_steps) matrix - 2GB at a million paths.
    """
    dt = t / n_steps
    drift = (r - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    z = rng.standard_normal((n_paths, n_steps))
    z *= vol
    z += drift
    np.cumsum(z, axis=1, out=z)
    np.exp(z, out=z)
    return float(np.maximum(s0 * z.mean(axis=1) - k, 0.0).sum())


def price_asian_option_np_threads(
    s0: float, k: float, r: float, sigma: float, t: float, n_steps: int, n_paths: int, seed: int
) -> float:
    """Price an arithmetic-average Asian call option by Monte Carlo, sharding the paths across a thread pool.

    numpy ufuncs are single-threaded, so multi-core numpy requires manual sharding. SeedSequence.spawn
    provides statistically independent RNG streams per shard. Threading parallelises even on GIL builds,
    because the large numpy operations release the GIL - so 3.14t makes little difference here.
    """
    counts = [n_paths // N_THREADS + (i < n_paths % N_THREADS) for i in range(N_THREADS)]
    rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(N_THREADS)]
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        sums = ex.map(lambda n, rng: _payoff_sum_np(s0, k, r, sigma, t, n_steps, n, rng), counts, rngs)
    return math.exp(-r * t) * sum(sums) / n_paths


@rust(
    py=False,
    dependencies=[
        rust_dependency("rand", version="0.9", features=["small_rng"]),
        rust_dependency("rand_distr", version="0.5"),
        rust_dependency("rayon", version="1.11"),
    ],
    imports=[
        "rand::{Rng, SeedableRng}",
        "rand::rngs::SmallRng",
        "rand_distr::StandardNormal",
        "rayon::prelude::*",
    ],
    profile={"strip": "symbols"},
)
def price_asian_option_rayon(
    s0: float,
    k: float,
    r: float,
    sigma: float,
    t: float,
    n_steps: Annotated[int, "usize"],
    n_paths: Annotated[int, "usize"],
    seed: Annotated[int, "u64"],
) -> float:  # ty: ignore[empty-body]
    """
    let dt = t / n_steps as f64;
    let drift = (r - 0.5 * sigma * sigma) * dt;
    let vol = sigma * dt.sqrt();
    // one independently-seeded RNG per path keeps the result deterministic regardless of scheduling
    let payoff_sum: f64 = (0..n_paths)
        .into_par_iter()
        .map(|i| {
            let mut rng = SmallRng::seed_from_u64(seed.wrapping_add(i as u64));
            let mut s = s0;
            let mut total = 0.0;
            for _ in 0..n_steps {
                let z: f64 = rng.sample(StandardNormal);
                s *= (drift + vol * z).exp();
                total += s;
            }
            (total / n_steps as f64 - k).max(0.0)
        })
        .sum();
    Ok((-r * t).exp() * payoff_sum / n_paths as f64)
    """


def main() -> None:
    """Run a performance comparison for varying numbers of simulated paths"""
    implementations = {
        "numpy+threads": price_asian_option_np_threads,
        "rust+rayon": price_asian_option_rayon,
    }

    # exclude the one-off module import overhead from the timings
    price_asian_option_rayon(S0, K, R, SIGMA, T, 1, 1, SEED)

    print("N | " + " | ".join(f"{name} (ms)" for name in implementations) + " | speedup")
    print("-:|" + "|".join("--------:" for _ in implementations) + "|--------:")

    for n_paths in [100_000, 300_000, 1_000_000]:
        prices: dict[str, float] = {}
        timings: dict[str, float] = {}
        for name, price in implementations.items():
            # use perf_counter not process_time: process_time sums CPU over all threads, hiding rayon's wall-clock gain
            start = perf_counter()
            prices[name] = price(S0, K, R, SIGMA, T, N_STEPS, n_paths, SEED)
            timings[name] = (perf_counter() - start) or 0.001

        # each implementation uses a different RNG stream, so estimates only agree statistically.
        # the payoff std dev is ~9 for these parameters, so this is a ~6 sigma bound on the spread
        assert max(prices.values()) - min(prices.values()) < 80.0 / math.sqrt(n_paths)

        speedup = timings["numpy+threads"] / timings["rust+rayon"] - 1.0
        print(
            f"{n_paths} | "
            + " | ".join(f"{timings[name] * 1000:.1f}" for name in implementations)
            + f" | {speedup:.0%}"
        )


if __name__ == "__main__":
    main()
