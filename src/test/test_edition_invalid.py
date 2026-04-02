import pytest

from xenoform_rs import XenoformRsError, rust


def test_edition_invalid() -> None:
    with pytest.raises(XenoformRsError):

        @rust(edition="2204")
        def f(i: int) -> bool:  # type: ignore[empty-body]
            "return i % 2;"

        f(3)


if __name__ == "__main__":
    test_edition_invalid()
