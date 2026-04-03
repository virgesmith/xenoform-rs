from typing import Annotated

import pytest

from xenoform_rs import rust


def test_fibonacci():
    with pytest.raises(FileNotFoundError):

        @rust(py=False, modules=["src/test/fibonacci.rs", "src/test/missing.rs"])
        def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty:ignore[empty-body]
            """
            Ok(fibonacci::fib(n))
            """

        assert fibonacci(10) == 55


if __name__ == "__main__":
    test_fibonacci()
