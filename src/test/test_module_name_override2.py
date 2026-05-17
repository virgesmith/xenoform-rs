from xenoform_rs import rust

# test_module1/2 will contain functions defined in both test_module_name_override.py and this file


@rust(py=False, module_name="test_module2")
def odd(i: int) -> bool:  # ty:ignore[empty-body]
    """
    Ok(i % 2 != 0)
    """


@rust(py=False, module_name="test_module1")
def even(i: int) -> bool:  # ty:ignore[empty-body]
    """
    Ok(i % 2 == 0)
    """


def test_multiple_module_names() -> None:
    assert odd(3)
    assert even(4)


if __name__ == "__main__":
    test_multiple_module_names()
