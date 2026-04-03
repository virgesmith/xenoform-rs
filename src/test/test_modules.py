from typing import Annotated

from xenoform_rs import rust


@rust(py=False, modules=["src/test/fibonacci.rs"], verbose=True)
def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty:ignore[empty-body]
    """
    Ok(fibonacci::fib(n))
    """


def test_fibonacci():
    assert fibonacci(10) == 55
    assert fibonacci(20) == 6765
    assert fibonacci(50) == 12586269025


if __name__ == "__main__":
    test_fibonacci()
