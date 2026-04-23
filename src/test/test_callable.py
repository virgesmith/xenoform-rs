from collections.abc import Callable
from typing import Annotated

import pytest

from xenoform_rs import rust


@rust(imports=["pyo3::types::{PyCFunction, PyDict, PyTuple}", "pyo3::exceptions::PyTypeError"])
def round_sign() -> Callable[[float, bool], int]:  # ty: ignore[empty-body]
    """
    // c.f. C++: return [](double x, bool s) -> int { return int(s ? -x : x); };

    PyCFunction::new_closure(py, None, None,
        move |args: &Bound<'_, PyTuple>, kwargs: Option<&Bound<'_, PyDict>>| -> PyResult<i32> {
        // Expect (float x, bool s) and nothing else
        if kwargs.is_some() || args.len() != 2 {
            return Err(PyTypeError::new_err("invalid arguments"));
        }
        let x = args.get_item(0)?.extract::<f64>()?;
        let s = args.get_item(1)?.extract::<bool>()?;
        let val = if s { -x } else { x };
        Ok(val as i32)
    })
    """


# this is the actual function, not one that returns it
def round_sign_py(x: float, s: bool) -> int:
    return int(-x if s else x)


@rust()
def modulo(n: int) -> Callable[[int], int]:  # ty: ignore[empty-body]
    """
    // c.f. C++: return [n](int i) { return i % n; };

    PyCFunction::new_closure(
        py,
        None,
        None,
        move |args: &Bound<'_, PyTuple>, kwargs: Option<&Bound<'_, PyDict>>| -> PyResult<i32> {
            if kwargs.is_some() || args.len() != 1 {
                return Err(PyTypeError::new_err("invalid arguments"));
            }
            let i = args.get_item(0)?.extract::<i32>()?;
            Ok(i % n)
        },
    )
    """


def modulo_py(n: int) -> Callable[[int], int]:
    return lambda i: i % n


@rust(py=False)
def use_modulo(f: Annotated[Callable[[int], int], "&Bound<'py, PyAny>"], i: int) -> int:  # ty: ignore[empty-body]
    """
    f.call1((i,))?.extract::<i32>()
    """


def rust_py(f: Callable[[int], int], i: int) -> int:
    return f(i)


@rust()
def use_round_sign(f: Annotated[Callable[[float, bool], int], "&Bound<'py, PyAny>"], x: float) -> int:  # ty: ignore[empty-body]
    """
    let args = (x, true).into_pyobject(py)?;
    f.call(args, None)?.extract::<i32>()
    """


def use_round_sign_py(f: Callable[[float, bool], int], x: float) -> int:
    return f(x, True)


def test_modulo() -> None:
    f = modulo(3)

    assert f(0) == 0
    assert f(2) == 2
    assert f(10) == 1

    with pytest.raises(TypeError):
        modulo("x")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        f("x")  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        f()  # ty: ignore[missing-argument]
    with pytest.raises(TypeError):
        f(2, 3)  # ty: ignore[too-many-positional-arguments]
    with pytest.raises(TypeError):
        f(2, z=3)  # ty: ignore[unknown-argument]

    assert modulo(2)(2) == modulo_py(2)(2) == 0
    assert modulo(3)(3) == modulo_py(3)(3) == 0
    assert modulo(5)(5) == modulo_py(5)(5) == 0
    assert modulo(5)(6) == modulo_py(5)(6) == 1


def test_use_modulo() -> None:
    assert use_modulo(modulo(5), 7) == 2
    # TypeError: argument 'f': 'function' object is not an instance of 'builtin_function_or_method'
    assert use_modulo(modulo_py(5), 7) == 2
    assert use_modulo(lambda n: n % 5, 7) == 2


def test_all_combinations() -> None:
    round_sign_lambda: Callable[[float, bool], int] = lambda x, s: int(-x if s else x)  # noqa: E731

    round_sign_rust = round_sign()

    assert round_sign_py(3.14, False) == round_sign_lambda(3.14, False) == round_sign_rust(3.14, False) == 3

    assert (
        use_round_sign_py(round_sign_py, 2.72)
        == use_round_sign_py(round_sign_lambda, 2.72)
        == use_round_sign_py(round_sign_rust, 2.72)
        == -2
    )

    assert (
        # TypeError: argument 'f': 'function' object is not an instance of 'builtin_function_or_method'
        use_round_sign(round_sign_rust, 2.72)
        == use_round_sign(round_sign_lambda, 2.72)
        == use_round_sign(round_sign_py, 2.72)
        == -2
    )


def test_function_type_errors() -> None:
    with pytest.raises(TypeError):
        use_round_sign(modulo, 1.0)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_round_sign_py(modulo, 1.0)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        use_round_sign(modulo_py, 1.0)  # ty: ignore[invalid-argument-type]

    with pytest.raises(TypeError):
        rust(round_sign, 1)  # ty: ignore[too-many-positional-arguments]
    with pytest.raises(TypeError):
        rust_py(round_sign, 1)  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        rust(round_sign_py, 1)  # ty: ignore[too-many-positional-arguments]


if __name__ == "__main__":
    test_all_combinations()
    # test_function_type_errors()
    # test_rust()
