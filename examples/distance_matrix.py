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
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"],
    profile={"strip": "symbols"},
)
def calc_dist_matrix_rust(
    points: Annotated[npt.NDArray[np.float64], "PyReadonlyArray2<f64>"],
) -> Annotated[npt.NDArray[np.float64], "Bound<'py, PyArray2<f64>>"]:  # ty: ignore[empty-body]
    """
    let points = points.as_array();
    let shape = points.shape();
    let (n, d) = (shape[0], shape[1]);

    let result = PyArray2::zeros(py, [n, n], false);
    let mut r = unsafe { result.as_array_mut() };

    for i in 0..n {
        for j in i + 1..n {
            let mut sum = 0.0;
            for k in 0..d {
                let diff = points.get([i, k]).unwrap() - points.get([j, k]).unwrap();
                sum += diff * diff;
            }
            let dist = sum.sqrt();
            if let Some(x) = r.get_mut([i, j]) {
                *x = dist;
            }
            if let Some(x) = r.get_mut([j, i]) {
                *x = dist;
            }
        }
    }
    Ok(result)
    """


if __name__ == "__main__":
    print("N | py (ms) | rust (ms) | speedup (%)")
    print("-:|--------:|----------:|-----------:")

    for size in [100, 300, 1000, 3000, 10000]:
        p = np.random.uniform(size=(size, 3))

        start = time.process_time()
        dist_p = calc_dist_matrix_py(p)
        elapsed_p = time.process_time() - start

        start = time.process_time()
        dist_r = calc_dist_matrix_rust(p)
        elapsed_r = time.process_time() - start

        assert np.abs(dist_r - dist_p).max() < 1e-15

        speedup = elapsed_p / elapsed_r - 1.0

        print(f"{size} | {elapsed_p * 1000:.1f} | {elapsed_r * 1000:.1f} | {speedup:.0%}")
