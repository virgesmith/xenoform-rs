import pytest

from xenoform_rs import rust
from xenoform_rs.config import get_config
from xenoform_rs.utils import get_function_scope, get_lib_path, load_rust_module


def outer(x: float) -> float:
    @rust(py=False)
    def inner(x: float, i: int) -> float:  # ty: ignore[empty-body]
        """
        Ok(x * i as f64)
        """

    return inner(x, 5)


def test_nested() -> None:
    assert outer(3.1) == 15.5

    module_dir = get_config().extmodule_root / "test_nested_ext"
    module = load_rust_module(get_lib_path(module_dir, "test_nested"), "test_nested")

    assert module._outer_inner(2.7, 3) == pytest.approx(8.1)


class Outer:
    class Inner:
        def method(self) -> None:
            pass


def test_get_function_scope() -> None:
    assert get_function_scope(test_nested) == ()
    # scopes are all lowercase, even if the class names are capitalized
    assert get_function_scope(Outer.Inner.method) == ("outer", "inner")


if __name__ == "__main__":
    # test_nested()
    test_get_function_scope()
