import pytest

from xenoform_rs import RustConfigError, rust


@rust(py=False, module_name="test_module1")
def odd(i: int) -> bool:  # ty:ignore[empty-body]
    """
    Ok(i % 2 != 0)
    """


@rust(py=False, module_name="test_module2")
def even(i: int) -> bool:  # ty:ignore[empty-body]
    """
    Ok(i % 2 == 0)
    """


def test_multiple_module_names() -> None:
    assert odd(3)
    assert even(4)


def test_invalid_module_name() -> None:
    with pytest.raises(RustConfigError):

        @rust(py=False, module_name="not valid")
        def h() -> None:
            "Ok(())"

        h()


if __name__ == "__main__":
    test_multiple_module_names()
    test_invalid_module_name()
