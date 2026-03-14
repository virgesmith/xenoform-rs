from xenoform_rs.utils import rust_dependency


def test_rust_dependency() -> None:
    assert rust_dependency("numpy") == "numpy", rust_dependency("numpy")
    assert rust_dependency("numpy", version="0.28") == 'numpy = { version = "0.28" }'
    assert (
        rust_dependency("pyo3", version="0.28", features=["extension-module", "abi3-py312"])
        == """pyo3 = { version = "0.28", features = ['extension-module', 'abi3-py312'] }"""
    )


if __name__ == "__main__":
    test_rust_dependency()
