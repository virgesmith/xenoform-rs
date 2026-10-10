import pytest

from xenoform_rs import CompilationError, rust


def test_edition_invalid() -> None:
    with pytest.raises(CompilationError, match="supported edition values") as excinfo:

        @rust(edition="2204")
        def f(i: int) -> bool:  # ty: ignore[empty-body]
            "return i % 2;"

        f(3)

    # cargo rejects the manifest before rustc runs, so the error comes from stderr
    assert excinfo.value.diagnostics == []


if __name__ == "__main__":
    test_edition_invalid()
