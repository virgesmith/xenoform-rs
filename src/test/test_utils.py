import pytest

from xenoform_rs import RustConfigError, rust_dependency


def test_rust_dependency() -> None:
    assert rust_dependency("num", "*") == 'num = "*"'
    assert rust_dependency("numpy", version="0.28") == 'numpy = { version = "0.28" }'
    assert (
        rust_dependency("pyo3", version="0.28", features=["extension-module", "abi3-py312"])
        == """pyo3 = { version = "0.28", features = ['extension-module', 'abi3-py312'] }"""
    )

    with pytest.raises(RustConfigError):
        rust_dependency("numpy")
    with pytest.raises(RustConfigError):
        rust_dependency("numpy", "*", features=["blah"])


if __name__ == "__main__":
    test_rust_dependency()
