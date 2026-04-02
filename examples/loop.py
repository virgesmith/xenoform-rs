"""Example of unvectorisable function performance - python vs inline rust"""

from time import process_time
from typing import Annotated

import numpy as np
import pandas as pd

from xenoform_rs import rust, rust_dependency


def calc_balances_py(data: pd.Series, rate: float) -> pd.Series:
    """Cannot vectorise, since each value is dependent on the previous value"""
    result = pd.Series(index=data.index)
    result_a = result.to_numpy()
    current_value = 0.0
    for i, value in data.items():
        current_value = (current_value + value) * (1 - rate)
        result_a[i] = current_value  # ty:ignore[invalid-assignment]
    return result


@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=[
        "numpy::{PyArray1, PyArrayMethods}",
        "pyo3::types::{PyDict, PyAnyMethods}",
    ],
    module_name="loop_rs",  # override as "loop" is a rust keyword
    profile={"strip": "symbols"},
)
def calc_balances_rust(
    data: Annotated[pd.Series, "Bound<'py, PyAny>"], rate: float
) -> Annotated[pd.Series, "Bound<'py, PyAny>"]:  # ty: ignore[empty-body]
    """
    // extract numpy arrays from the series. Note input is i64, output is f64
    let data_np = data.call_method0("to_numpy")?;
    let data_a: &Bound<'py, PyArray1<i64>> = data_np.cast()?;
    let a = unsafe { data_a.as_array() };
    let n = a.len();

    let mut r = vec![0.0; n];
    let mut current_value = 0.0;

    for i in 0..n {
        current_value = (current_value + a[i] as f64) * (1.0 - rate);
        r[i] = current_value;
    }

    // Construct a pd.Series with the same index as the input
    let result_np = PyArray1::from_slice(py, &r);
    let kwargs = PyDict::new(py);
    kwargs.set_item("index", data.getattr("index")?)?;

    let pd = py.import("pandas")?;
    let result = pd.getattr("Series")?.call((result_np,), Some(&kwargs))?;

    Ok(result)
    """


def main() -> None:
    """Run a performance comparison for varying series lengths"""
    rng = np.random.default_rng(19937)
    rate = 0.001

    print("N | py (ms) | rust (ms) | speedup (%)")
    print("-:|--------:|----------:|-----------:")
    for n in [1000, 10000, 100000, 1000000, 10000000]:
        data = pd.Series(index=range(n), data=rng.integers(-100, 101, size=n), name="cashflow")

        start = process_time()
        py_result = calc_balances_py(data, rate)
        py_time = process_time() - start

        start = process_time()
        # Although pyo3/rust doesn't understand the type pd.Series, it can use the py::object API to manipulate
        # and create instances of this type
        rust_result = calc_balances_rust(data, rate)
        rust_time = process_time() - start

        print(f"{n} | {py_time * 1000:.1f} | {rust_time * 1000:.1f} | {100 * (py_time / rust_time - 1.0):.0f}")
        assert py_result.equals(rust_result)


if __name__ == "__main__":
    main()
