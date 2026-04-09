import pytest

from xenoform_rs import RustConfigError, rust


def test_edition_invalid() -> None:
    with pytest.raises(RustConfigError):

        @rust(edition="2204")
        def f(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 2;"

        f(3)


if __name__ == "__main__":
    test_edition_invalid()
