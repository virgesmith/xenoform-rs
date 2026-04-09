import pytest

from xenoform_rs import RustConfigError, rust


def test_profile_conflict() -> None:

    with pytest.raises(RustConfigError, match="Conflicting profile values for opt-level: 3 vs 2"):

        @rust(py=False, profile={"opt-level": "3", "debug": "none"})
        def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
            "if i > j { Ok(i) } else { Ok(j) }"

        @rust(py=False, profile={"opt-level": "2"})
        def min(i: int, j: int) -> int:  # ty: ignore[empty-body]
            "if i > j { Ok(i) } else { Ok(j) }"

        assert max(2, 3) == min(3, 4)


if __name__ == "__main__":
    test_profile_conflict()
