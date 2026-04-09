from typing import Annotated

import pytest

from xenoform_rs import RustTypeError, rust
from xenoform_rs.extension_types import translate_type


def test_translate_compound_types() -> None:
    with pytest.raises(RustTypeError):
        translate_type(int | float)  # ty:ignore[invalid-argument-type]
    with pytest.raises(RustTypeError):
        translate_type(int | float | None)  # ty:ignore[invalid-argument-type]
    assert str(translate_type(int | None)) == "Option<i32>"  # ty: ignore[invalid-argument-type]
    assert str(translate_type(Annotated[int | float, "f64"])) == "f64"  # ty: ignore[invalid-argument-type]
    assert str(translate_type(Annotated[int | None, "&Bound<'_, PyAny>"])) == "&Bound<'_, PyAny>"  # ty: ignore[invalid-argument-type]


@rust(py=False)
def tuple_type(x: tuple[int, tuple[float, bool]]) -> str:  # ty:ignore[empty-body]
    """
    Ok(format!("x=({}, ({}, {}))", x.0, x.1.0, x.1.1))
    """


def test_tuple_type() -> None:
    assert tuple_type((1, (2.3, True))) == "x=(1, (2.3, true))"
    # ints get implicitly cast to float
    assert tuple_type((1, (2, True))) == "x=(1, (2, true))"
    # and bool to int
    assert tuple_type((True, (2, False)))
    # but non-type-safe casts get flagged
    with pytest.raises(TypeError):
        assert tuple_type((1.23, (2, False)))  # ty:ignore[invalid-argument-type]


@rust(py=False)
def optional_type(x: int | None) -> int:  # ty: ignore[empty-body]
    """
    Ok(x.unwrap_or(42))
    """


def test_optional_type() -> None:
    assert optional_type(1) == 1
    assert optional_type(None) == 42


@rust(py=False)
def overridden_compound_type(x: Annotated[int | float, "f64"]) -> float:  # ty: ignore[empty-body]
    """
    Ok(x)
    """


def test_compound_type() -> None:
    assert overridden_compound_type(1.0) == 1.0
    assert overridden_compound_type(12345) == 12345.0
    # too big to fit into a float
    with pytest.raises(OverflowError):
        overridden_compound_type(10**310)


if __name__ == "__main__":
    test_translate_compound_types()
    test_tuple_type()
    test_optional_type()
    test_compound_type()
