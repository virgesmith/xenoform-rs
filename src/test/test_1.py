from typing import Annotated

import pytest

from xenoform_rs.compile import rust

# TODO temporatry - remove when other tests give adequate coverage


@rust(py=False, verbose=True)
def add_numbers(a: Annotated[int, "u32"], b: Annotated[int, "u32"]) -> Annotated[int, "u32"]:  # type: ignore[empty-body]
    """
    Ok(a + b)
    """


def test_add_numbers():
    assert add_numbers(5, 3) == 8
    assert add_numbers(10, 20) == 30
    with pytest.raises(OverflowError, match="out of range integral type conversion attempted"):
        add_numbers(-1, 5)


@rust(py=False, verbose=True)
def multiply_and_subtract(x: float, y: float, z: float) -> float:  # type: ignore[empty-body]
    """
    //Calculates (x * y) - z in Rust.
    Ok((x * y) - z)
    """


def test_multiply_and_subtract():
    assert multiply_and_subtract(2.5, 4.0, 1.0) == 9.0
    assert multiply_and_subtract(10.0, 0.5, 3.0) == 2.0


@rust(py=False, verbose=True)
def greet(name: str) -> str:  # type: ignore[empty-body]
    """
    //Returns a greeting message from Rust.
    Ok(format!("Hello from Rust, {}!", name))
    """


def test_greet():
    assert greet("World") == "Hello from Rust, World!"
    assert greet("Rustacean") == "Hello from Rust, Rustacean!"


# --- Test the functions ---
if __name__ == "__main__":
    test_add_numbers()
    test_multiply_and_subtract()
    test_greet()
