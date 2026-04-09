import inspect
from typing import Annotated

import pytest

from xenoform_rs.compile import _check_annotations, rust
from xenoform_rs.errors import AnnotationError


@rust(py=False)
def f(_i: int, _x: float, *, _b: bool) -> str:  # ty: ignore[empty-body]
    """
    Ok(String::from("hello"))
    """


def test_typing() -> None:
    # check the compile machinery doesn't lose any type information
    def wrap_f(i: Annotated[int, "size_t"], x: float, *, b: bool) -> str:
        # the real test here is the linters (mypy ruff etc) not pytest. there should be no errors about the types
        # differing between wrap_f and f
        return f(i, x, _b=b)

    assert wrap_f(42, 1.0, b=True) == "hello"
    sig = inspect.signature(f)
    assert sig.return_annotation is str
    assert "_i" in sig.parameters and sig.parameters["_i"].annotation is int
    assert "_x" in sig.parameters and sig.parameters["_x"].annotation is float
    assert "_b" in sig.parameters and sig.parameters["_b"].annotation is bool


def untyped(x, y: Annotated[int, "blah"]):
    pass


def untyped_return(x: int, y: Annotated[int, "blah"]):
    pass


def typed_noargs() -> None:
    pass


def test_untyped() -> None:
    with pytest.raises(AnnotationError):
        _check_annotations(untyped)
    with pytest.raises(AnnotationError):
        _check_annotations(untyped_return)
    _check_annotations(typed_noargs)


if __name__ == "__main__":
    test_untyped()
