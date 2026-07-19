"""Example of custom vectorised function performance - python vs inline rust"""

import time
from typing import Annotated

import numpy as np
import numpy.typing as npt

from xenoform_rs import rust, rust_dependency


def calc_dist_matrix_py(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))


@rust(
    dependencies=[
        rust_dependency("numpy", version="0.28"),
        rust_dependency("rayon", version="1.11"),
    ],
    imports=[
        "numpy::{PyArray1, PyArray2, PyArrayMethods, PyReadonlyArray2}",
        "rayon::prelude::*",
    ],
    profile={"strip": "symbols"},
)
def calc_dist_matrix_rust(
    points: Annotated[npt.NDArray[np.float64], "PyReadonlyArray2<f64>"],
) -> Annotated[npt.NDArray[np.float64], "Bound<'py, PyArray2<f64>>"]:  # ty: ignore[empty-body]
    """
    let points = points.as_array();
    let shape = points.shape();
    let (n, d) = (shape[0], shape[1]);

    // fill a plain Vec in parallel: each row is a disjoint chunk, so there are no races
    // and no need to mirror the upper triangle across threads.
    let mut data = vec![0.0f64; n * n];
    data.par_chunks_mut(n).enumerate().for_each(|(i, row)| {
        for j in 0..n {
            let mut sum = 0.0;
            for k in 0..d {
                let diff = points[[i, k]] - points[[j, k]];
                sum += diff * diff;
            }
            row[j] = sum.sqrt();
        }
    });

    let result = PyArray1::from_vec(py, data).reshape([n, n])?;
    Ok(result)
    """


if __name__ == "__main__":
    # exclude the one-off module import and rayon threadpool spin-up from the timings
    calc_dist_matrix_rust(np.random.uniform(size=(2, 3)))

    print("N | py (ms) | rust (ms) | speedup")
    print("-:|--------:|----------:|-----------:")

    for size in [100, 300, 1000, 3000, 10000]:
        p = np.random.uniform(size=(size, 3))

        start = time.perf_counter()
        dist_p = calc_dist_matrix_py(p)
        elapsed_p = time.perf_counter() - start

        start = time.perf_counter()
        dist_r = calc_dist_matrix_rust(p)
        # windows perf_counter() is inaccurate
        elapsed_r = (time.perf_counter() - start) or 1.0

        assert np.abs(dist_r - dist_p).max() < 1e-15

        speedup = elapsed_p / elapsed_r - 1.0

        print(f"{size} | {elapsed_p * 1000:.1f} | {elapsed_r * 1000:.1f} | {speedup:.0%}")
