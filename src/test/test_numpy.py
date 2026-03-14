from typing import Annotated

import numpy as np
import numpy.typing as npt

from xenoform_rs import rust, rust_dependency


# PyArrayDyn must be passed by bound ref
@rust(
    py=False,
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArrayDyn, PyArrayMethods}"],
)
def by_ref(a: Annotated[npt.NDArray[np.float64], "&Bound<'py, PyArrayDyn<f64>>"]) -> None:
    """
    let mut a = unsafe { a.as_array_mut() };
    if let Some(x) = a.get_mut([0, 0]) {
        *x = 1.0;
    }
    Ok(())
    """


def test_numpy_byref() -> None:
    a = np.zeros((2, 2))
    by_ref(a)
    assert a[0, 0] == 1.0
    assert a.sum() == 1.0


# PyReadonlyArrayDyn can be passed (moved?) by value but data can be mutated (through a shallow copy?)
@rust(
    py=False,
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::PyReadonlyArrayDyn"],
)
def by_val(a: npt.NDArray[np.float64]) -> None:
    """
    let mut a = unsafe { a.as_array_mut() };
    a += 1.0;
    // or
    // for x in a.iter_mut() {
    //     *x += 1.0;
    // }
    Ok(())
    """


def test_numpy_byval() -> None:
    a = np.zeros((2, 2))
    by_val(a)
    assert (a == 1.0).all()


@rust(py=False)
def specify_int_bits(a: npt.NDArray[np.int32]) -> np.int64:  # ty: ignore[empty-body]
    """
    Ok(a.as_array().ndim() as i64)
    """


def test_int_bits() -> None:
    a = np.zeros((2, 2, 2), dtype=np.int32)

    assert specify_int_bits(a) == 3


@rust(imports=["numpy::IntoPyArray"])
def daxpy(
    a: float, x: npt.NDArray[np.float64], y: npt.NDArray[np.float64]
) -> Annotated[npt.NDArray[np.float64], "Bound<'py, PyArrayDyn<f64>>"]:  # ty: ignore[empty-body]
    """
    let x = x.as_array();
    let y = y.as_array();
    let z = a * &x + &y;
    Ok(z.into_pyarray(py))
    """


def test_daxpy() -> None:
    a = 12.0
    x = np.ones((4, 4))
    y = np.full((4, 4), 30.0)

    assert (daxpy(a, x, y) == 42.0).all()


# #[pyfunction(name = "axpy")]
# fn axpy_py<'py>(
#     py: Python<'py>,
#     a: f64,
#     x: PyReadonlyArrayDyn<'py, f64>,
#     y: PyReadonlyArrayDyn<'py, f64>,
# ) -> Bound<'py, PyArrayDyn<f64>> {
#     let x = x.as_array();
#     let y = y.as_array();
#     let z = axpy(a, x, y);
#     z.into_pyarray(py)
# }


if __name__ == "__main__":
    test_numpy_byref()
    test_numpy_byval()
    test_daxpy()
