import pytest

from xenoform_rs import RustConfigError, rust


def test_profile_invalid() -> None:
    with pytest.raises(RustConfigError):

        @rust(py=False, profile={"opt-level": "4"})
        def f(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 2;"

        f(3)


if __name__ == "__main__":
    test_profile_invalid()
