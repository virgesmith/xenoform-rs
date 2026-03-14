from typing import Annotated, Any

import pytest

from xenoform_rs import rust


@rust(py=False)
def f_rust(n: int, /, x: float, y: float = 2.7, *, b: bool = False) -> str:  # type: ignore[empty-body]
    # arg optional positional keyword
    #   n    N         Y         N
    #   x    N         Y         Y
    #   y    Y         Y         Y
    #   b    Y         N         Y
    """
    Ok(format!("n={} x={} y={} b={}", n, x, y, b))
    """


def test_pos_kwargs() -> None:
    with pytest.raises(TypeError):
        f_rust(1)  # type: ignore[call-arg]
    assert f_rust(1, 3.1) == "n=1 x=3.1 y=2.7 b=false"
    assert f_rust(1, 3.1, 3.1) == "n=1 x=3.1 y=3.1 b=false"
    assert f_rust(1, x=3.1) == "n=1 x=3.1 y=2.7 b=false"
    assert f_rust(1, x=3.1, y=3.1) == "n=1 x=3.1 y=3.1 b=false"
    with pytest.raises(TypeError):
        f_rust(n=1, x=3.1)  # type: ignore[call-arg]
    assert f_rust(1, 3.1, b=True) == "n=1 x=3.1 y=2.7 b=true"
    assert f_rust(1, b=True, x=2.7) == "n=1 x=2.7 y=2.7 b=true"
    with pytest.raises(TypeError):
        f_rust(1, 3.1, 2.7, True)  # type: ignore[misc]


@rust(py=False)
def varargs(*args: Any) -> Annotated[int, "usize"]:  # type: ignore[empty-body]
    """
    Ok(args.len())
    """


def test_varargs() -> None:
    assert varargs() == 0
    assert varargs(5) == 1
    assert varargs(5, 3) == 2
    with pytest.raises(TypeError):
        varargs(x=5)  # type: ignore[call-arg]


@rust(py=False, imports=["pyo3::types::{PyDict, PyTuple, PyTupleMethods, PyDictMethods}"])
def varkwargs(**args: Any) -> Annotated[int, "usize"]:  # type: ignore[empty-body]
    """
    Ok(match args {
        Some(dict) => dict.len(),
        None => 0
    })
    """


def test_varkwargs() -> None:
    assert varkwargs() == 0
    assert varkwargs(x=1) == 1
    assert varkwargs(x=1, y=2) == 2
    with pytest.raises(TypeError):
        varkwargs(5)  # type: ignore[call-arg]


@rust(py=False)
def varposkwargs(n: int, *args: Any, m: int, **kwargs: Any) -> int:  # type: ignore[empty-body]
    """
    let kwargs_len = match kwargs {
        Some(dict) => dict.len() as i32,
        None => 0
    };
    Ok(args.len() as i32 + 10 * kwargs_len + 100 * n + 1000 * m)
    """


def test_varposkwargs() -> None:
    with pytest.raises(TypeError):
        assert varposkwargs(1, 1)  # type: ignore[call-arg]
    assert varposkwargs(1, m=1) == 1100
    assert varposkwargs(n=1, m=1) == 1100
    assert varposkwargs(1, 1, m=1, y=2) == 1111
    assert varposkwargs(1, m=1, y=2) == 1110
    assert varposkwargs(1, 1, m=1) == 1101


if __name__ == "__main__":
    test_pos_kwargs()
    test_varargs()
    test_varkwargs()
    test_varposkwargs()
