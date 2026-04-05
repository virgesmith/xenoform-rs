import pytest

from xenoform_rs import RustTypeError, rust


def test_compound_type_error() -> None:

    with pytest.raises(RustTypeError):

        @rust(py=False)
        def compound_type(_x: int | str) -> None:
            """
            Ok(())
            """

        compound_type(1)


if __name__ == "__main__":
    test_compound_type_error()
