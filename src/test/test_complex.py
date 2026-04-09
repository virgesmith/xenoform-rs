from math import exp, pi

import numpy as np
import pytest

from xenoform_rs import rust, rust_dependency

# @rust()
# def complex_float_func(z: np.complex64) -> np.complex64:
#     """
#     Ok(z.into().powc(z))
#     """


@rust(dependencies=[rust_dependency("num", "*")], imports=["pyo3::types::PyComplex", "num::complex::Complex"])
def complex_double_func(z: complex) -> complex:  # ty: ignore[empty-body]
    """
    let z = Complex::<f64>::new(z.real(), z.imag());
    let z = z.powc(z);
    Ok(PyComplex::from_doubles(py, z.re, z.im))
    """


def test_complex_double() -> None:
    # i^i = e^(-pi/2)
    assert complex_double_func(1j) == pytest.approx(exp(-pi / 2))
    assert complex_double_func(np.complex128(0, 1)) == pytest.approx(exp(-pi / 2))
    # assert complex_double_func(np.complex64(0, 1)) == pytest.approx(exp(-pi / 2))
    # assert complex_double_func(2.0) == 4


# def test_complex_float() -> None:
#     assert complex_float_func(1j) == pytest.approx(exp(-pi / 2))
#     assert complex_float_func(np.complex128(0, 1)) == pytest.approx(exp(-pi / 2))
#     assert complex_float_func(np.complex64(0, 1)) == pytest.approx(exp(-pi / 2))
#     assert complex_float_func(2) == 4


if __name__ == "__main__":
    # test_complex_float()
    test_complex_double()
