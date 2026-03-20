from xenoform_rs import rust


# TODO make the arg an Iterable?
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
def dict_sum(d: dict[int, int]) -> int:  # type: ignore[empty-body]
    """
    Ok(d.values().sum())
    """


def test_dict() -> None:
    assert dict_sum({i: i + 1 for i in range(4)}) == 10


@rust(py=False)
def tuple_sum(t4: tuple[int, int, int, int]) -> int:  # type: ignore[empty-body]
    """
    // summing a C++ tuple is not straightforward
    Ok(t4.0 + t4.1 + t4.2 + t4.3)
    """


def test_tuple() -> None:
    assert tuple_sum((1, 2, 3, 4)) == 10


@rust(py=False)
def frozenset_length(s: frozenset[int]) -> int:  # type: ignore[empty-body]
    """
    Ok(s.len() as i32)
    """


def test_frozenset() -> None:
    assert frozenset_length(frozenset((1, 2, 3, 1))) == 3
    assert frozenset_length({1, 2, 3, 1}) == 3  # type: ignore[arg-type] # noqa: B033


if __name__ == "__main__":
    test_vector()
    test_set()
    test_dict()
    test_tuple()
    test_frozenset()
