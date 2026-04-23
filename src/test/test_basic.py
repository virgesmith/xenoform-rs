from collections.abc import Callable
from typing import Annotated, Any

import pytest

from xenoform_rs.compile import _check_build_fetch_module_impl, rust
from xenoform_rs.errors import RustTypeError, XenoformRsError
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import translate_function_signature


def test_signature_translation1() -> None:
    def f(_i: int) -> None:
        ""

    assert translate_function_signature(f, py=False) == ("(_i: i32) -> PyResult<()>", ["_i"])
    assert translate_function_signature(f, py=True) == ("(py: Python<'py>, _i: i32) -> PyResult<()>", ["_i"])

    def f2(a: float, b: str, c: bool) -> int:  # ty: ignore[empty-body]
        pass

    assert translate_function_signature(f2, py=True) == (
        "(py: Python<'py>, a: f64, b: String, c: bool) -> PyResult<i32>",
        ["a", "b", "c"],
    )

    def f3(a: float, b: Annotated[str, "&str"], c: bool) -> int:  # ty: ignore[empty-body]
        pass

    assert translate_function_signature(f3, py=True) == (
        "(py: Python<'py>, a: f64, b: &str, c: bool) -> PyResult<i32>",
        ["a", "b", "c"],
    )

    def f4(*args: Any) -> bool:  # ty: ignore[empty-body]
        pass

    assert translate_function_signature(f4, py=True) == (
        "(py: Python<'py>, args: &Bound<'py, PyTuple>) -> PyResult<bool>",
        ["*args"],
    )

    def f5(a: float, *, b: Annotated[str, "&str"], c: bool, **kwargs: Any) -> int:  # ty: ignore[empty-body]
        pass

    assert translate_function_signature(f5, py=True) == (
        "(py: Python<'py>, a: f64, b: &str, c: bool, kwargs: Option<&Bound<'py, PyDict>>) -> PyResult<i32>",
        ["a", "*", "b", "c", "**kwargs"],
    )


def test_signature_translation2() -> None:
    def f0() -> None:
        pass

    assert translate_function_signature(f0, py=False) == (
        "() -> PyResult<()>",
        [],
    )

    def f6(a: float, /, b: bool, *, c: int) -> None:
        pass

    assert translate_function_signature(f6, py=True) == (
        "(py: Python<'py>, a: f64, b: bool, c: i32) -> PyResult<()>",
        ["a", "/", "b", "*", "c"],
    )

    def f7(*, c: int) -> None:
        pass

    assert translate_function_signature(f7, py=True) == ("(py: Python<'py>, c: i32) -> PyResult<()>", ["*", "c"])

    def f8(a: float, c: int, /) -> None:
        ""

    assert translate_function_signature(f8, py=True) == (
        "(py: Python<'py>, a: f64, c: i32) -> PyResult<()>",
        ["a", "c", "/"],
    )

    def f9(a: float, *, c: bool = True) -> None:
        ""

    assert translate_function_signature(f9, py=True) == (
        "(py: Python<'py>, a: f64, c: bool) -> PyResult<()>",
        ["a", "*", "c=true"],
    )

    def f10(a: tuple[int, tuple[int, float]], *, value: Callable[[int, float], bool]) -> bool:  # ty:ignore[empty-body]
        ""

    assert translate_function_signature(f10, py=True) == (
        "(py: Python<'py>, a: (i32, (i32, f64)), value: &Bound<'py, PyCFunction>) -> PyResult<bool>",
        ["a", "*", "value"],
    )

    # optional types inside tuple are tricky
    def f11(a: tuple[tuple[int, bool | None], float | None]) -> None:
        ""

    assert translate_function_signature(f11, py=False) == (
        "(a: ((i32, Option<bool>), Option<f64>)) -> PyResult<()>",
        ["a"],
    )

    # check ref stripped from return type even when overridden
    def f12(some: bool) -> Annotated[dict[str, int] | None, "Option<&Bound<'py, PyDict>>"]:
        ""

    assert translate_function_signature(f12, py=False) == (
        "(some: bool) -> PyResult<Option<Bound<'py, PyDict>>>",
        ["some"],
    )


@rust(py=False)
def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
    # comments can be added before...
    "if i > j { Ok(i) } else { Ok(j) }"
    # ...and after the docstr


def test_basic() -> None:
    assert max(2, 3) == 3


@rust(py=False)
def passref(b: bytes) -> int:  # ty: ignore[empty-body]
    """
    Ok(b.len() as i32)
    """


def test_ref() -> None:
    b = b"sjksjdlk"
    passref(b)


@rust(py=False, imports=["pyo3::exceptions::PyRuntimeError"])
def throws() -> bool:  # ty: ignore[empty-body]
    """
    Err(PyRuntimeError::new_err("oops"))
    """


def test_throws() -> None:
    with pytest.raises(RuntimeError):
        throws()


def test_unknown_type() -> None:
    with pytest.raises(RustTypeError):

        class X: ...

        @rust()
        def unknown(x: X) -> bool:  # ty: ignore[empty-body]
            "false"


def test_compile_error() -> None:
    f = "{#error}"
    spec = ModuleSpec().add_function(FunctionSpec(name="error", py=True, body=f, arg_annotations="", scope=()))
    with pytest.raises(XenoformRsError):
        _check_build_fetch_module_impl("broken_module", spec)


if __name__ == "__main__":
    # test_signature_translation2()
    test_ref()
