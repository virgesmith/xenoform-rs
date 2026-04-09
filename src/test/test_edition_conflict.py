import pytest

from xenoform_rs import rust


def test_edition_conflict() -> None:

    with pytest.raises(ValueError, match="Incompatible edition values: 2024 when 2021 has already been set"):

        @rust(py=False, edition="2021")
        def max(i: int, j: int) -> int:  # ty: ignore[empty-body]
            # comments can be added before...
            "if i > j { Ok(i) } else { Ok(j) }"
            # ...and after the docstr

        @rust(py=False, edition="2024")
        def min(i: int, j: int) -> int:  # ty: ignore[empty-body]
            # comments can be added before...
            "if i > j { Ok(i) } else { Ok(j) }"
            # ...and after the docstr

        assert max(2, 3) == min(3, 4)


if __name__ == "__main__":
    test_edition_conflict()
