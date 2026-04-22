from typing import Annotated

from xenoform_rs import rust


@rust(py=False)
def vector_sum(v: list[int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(v.iter().sum())
    """


def test_vector() -> None:
    assert vector_sum([1, 2, 3, 4]) == 10
    assert vector_sum(range(5)) == 10  # ty:ignore[invalid-argument-type]


@rust(py=False, imports=["std::collections::HashSet"])
def set_sum(s: set[int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(s.iter().sum())
    """


def test_set() -> None:
    assert set_sum({1, 2, 3, 4}) == 10


@rust(py=False, imports=["std::collections::HashMap"])
def dict_sum(d: dict[int, int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(d.values().sum())
    """


def test_dict() -> None:
    assert dict_sum({i: i + 1 for i in range(4)}) == 10


@rust(py=False)
def tuple_sum(t4: tuple[int, int, int, int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(t4.0 + t4.1 + t4.2 + t4.3)
    """


def test_tuple() -> None:
    assert tuple_sum((1, 2, 3, 4)) == 10


@rust(py=False)
def frozenset_length(s: frozenset[int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(s.len() as i32)
    """


def test_frozenset() -> None:
    assert frozenset_length(frozenset((1, 2, 3, 1))) == 3
    assert frozenset_length({1, 2, 3, 1}) == 3  # ty: ignore[invalid-argument-type] # noqa: B033


@rust(py=False, imports=["std::collections::HashMap"])
def return_dict() -> dict[str, int]:  # ty: ignore[empty-body]
    """
    let mut result = HashMap::<String, i32>::new();
    result.insert("x".to_string(), 42);
    Ok(result)
    """


def test_return_dict() -> None:
    assert return_dict() == {"x": 42}


@rust(py=False, imports=["std::collections::HashMap"])
def return_optional_dict(some: bool) -> dict[str, int] | None:
    """
    if !some {
        return Ok(None);
    }
    let mut result = HashMap::<String, i32>::new();
    result.insert("x".to_string(), 42);
    Ok(Some(result))
    """


def test_return_optional_dict() -> None:
    assert return_optional_dict(False) is None
    assert return_optional_dict(True) == {"x": 42}


@rust(imports=["pyo3::types::PyDict"])
def return_overridden_optional_dict(some: bool) -> Annotated[dict[str, int] | None, "Option<Bound<'py, PyDict>>"]:
    """
    if !some {
        return Ok(None);
    }
    let result = PyDict::new(py);
    result.set_item("x", 42)?;
    Ok(Some(result))
    """


def test_return_overidden_optional_dict() -> None:
    assert return_overridden_optional_dict(False) is None
    assert return_overridden_optional_dict(True) == {"x": 42}


if __name__ == "__main__":
    test_vector()
    test_set()
    test_dict()
    test_tuple()
    test_frozenset()
    test_return_dict()
    test_return_optional_dict()
    test_return_overidden_optional_dict()
