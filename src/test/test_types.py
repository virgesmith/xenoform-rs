from typing import Annotated

import numpy as np
import numpy.typing as npt
import pytest

from xenoform_rs.compile import rust
from xenoform_rs.errors import RustTypeError
from xenoform_rs.extension_types import PyTypeTree, parse_annotation, translate_type


def test_basic_types() -> None:
    rusttype = translate_type(int)
    assert str(rusttype) == "i32"

    rusttype = translate_type(float)
    assert str(rusttype) == "f64"

    rusttype = translate_type(bool)
    assert str(rusttype) == "bool"

    rusttype = translate_type(str)
    assert str(rusttype) == "String"

    rusttype = translate_type(bytes)
    assert str(rusttype) == "&'py [u8]"


def test_pytypetree_basic_types() -> None:
    tree = PyTypeTree(int)
    assert tree.type is int
    assert tree.subtypes == ()
    assert repr(tree) == "int"

    tree = PyTypeTree(float)
    assert tree.type is float
    assert tree.subtypes == ()
    assert repr(tree) == "float"

    tree = PyTypeTree(str)
    assert tree.type is str
    assert tree.subtypes == ()
    assert repr(tree) == "str"


def test_pytypetree_generic_types() -> None:
    tree = PyTypeTree(list[int])
    assert tree.type is list
    assert len(tree.subtypes) == 1
    assert tree.subtypes[0].type is int
    assert repr(tree) == "list[int]"

    tree = PyTypeTree(dict[str, float])
    assert tree.type is dict
    assert len(tree.subtypes) == 2
    assert tree.subtypes[0].type is str
    assert tree.subtypes[1].type is float
    assert repr(tree) == "dict[str, float]"


def test_pytypetree_tuple_and_ellipsis() -> None:
    tree = PyTypeTree(tuple[int, ...])
    assert tree.type is tuple
    assert len(tree.subtypes) == 2
    assert tree.subtypes[0].type is int
    assert tree.subtypes[1].type is Ellipsis
    assert repr(tree.subtypes[1]) == "..."


def test_pytypetree_raises_on_annotated() -> None:
    with pytest.raises(TypeError):
        PyTypeTree(Annotated[int, "foo"])  # ty: ignore[invalid-argument-type]


def test_specialised_types() -> None:
    rusttype = translate_type(list[int])
    assert str(rusttype) == "Vec<i32>"

    rusttype = translate_type(list[float])
    assert str(rusttype) == "Vec<f64>"

    rusttype = translate_type(set[str])
    assert str(rusttype) == "HashSet<String>"

    rusttype = translate_type(dict[str, list[bool]])
    assert str(rusttype) == "HashMap<String, Vec<bool>>"


def test_numpy_types() -> None:
    rusttype = translate_type(npt.NDArray[np.int32])
    assert str(rusttype) == "PyReadonlyArrayDyn<i32>"

    rusttype = translate_type(npt.NDArray[np.float64])
    assert str(rusttype) == "PyReadonlyArrayDyn<f64>"


def test_user_type() -> None:
    class X: ...

    with pytest.raises(RustTypeError):

        @rust()
        def process_x(x: X) -> None:
            "Ok(())"

        process_x(X())

    @rust(py=False)
    def process_x_annotated(_x: Annotated[X, "&Bound<'py, PyAny>"]) -> None:
        "Ok(())"

    process_x_annotated(X())


def test_parse_annotation() -> None:
    t, q = parse_annotation(int)
    assert t is int
    assert q == {}

    t, q = parse_annotation(Annotated[int, "i64"])  # ty: ignore[invalid-argument-type]
    assert t is int
    assert q == {"override": "i64"}

    t, q = parse_annotation(Annotated[int, "u32"])  # ty: ignore[invalid-argument-type]
    assert t is int
    assert q == {"override": "u32"}

    with pytest.raises(TypeError):
        parse_annotation(Annotated[int, 42])  # ty: ignore[invalid-argument-type]


def test_overridden_annotated_types() -> None:
    rusttype = translate_type(Annotated[int, "u32"])  # ty: ignore[invalid-argument-type]
    assert str(rusttype) == "u32"

    rusttype = translate_type(Annotated[list[int], "&Bound<'py, PyList>"])  # ty: ignore[invalid-argument-type]
    assert str(rusttype) == "&Bound<'py, PyList>"


@rust(py=False)
def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty: ignore[empty-body]
    """
    fn fib_impl(n: u64) -> u64 {
        match n {
            0 | 1 => n,
            _ => fib_impl(n - 1) + fib_impl(n - 2),
        }
    }
    Ok(fib_impl(n))
    """


def test_unsigned() -> None:
    assert fibonacci(10) == 55
    with pytest.raises(OverflowError):
        fibonacci(-10)
