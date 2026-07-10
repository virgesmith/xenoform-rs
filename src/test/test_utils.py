import sys
from pathlib import Path

import pytest

from xenoform_rs import RustConfigError, rust_dependency, utils
from xenoform_rs.errors import RustModuleError


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


def test_rustfmt_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    code = "fn main() {}"

    def raise_oserror(*_args: object, **_kwargs: object) -> None:
        raise OSError("rustfmt not found")

    monkeypatch.setattr(utils.subprocess, "run", raise_oserror)
    assert utils.rustfmt(code) == code

    class FailedResult:
        returncode = 1
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(utils.subprocess, "run", lambda *_args, **_kwargs: FailedResult())
    assert utils.rustfmt(code) == code


def test_get_lib_path_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    module_dir = Path("/some/module")
    release = module_dir / "target" / utils.python_abi_tag() / "release"

    monkeypatch.setattr(sys, "platform", "darwin")
    assert utils.get_lib_path(module_dir, "mod") == release / "libmod.dylib"

    monkeypatch.setattr(sys, "platform", "win32")
    assert utils.get_lib_path(module_dir, "mod") == release / "mod.dll"

    monkeypatch.setattr(sys, "platform", "sunos5")
    with pytest.raises(RustConfigError):
        utils.get_lib_path(module_dir, "mod")


def test_load_rust_module_invalid_lib(tmp_path: Path) -> None:
    junk = tmp_path / "junk_lib.so"
    junk.write_bytes(b"not a shared library")
    with pytest.raises(RustModuleError):
        utils.load_rust_module(junk, "junk_lib")


def test_load_rust_module_no_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(utils, "spec_from_loader", lambda *_args, **_kwargs: None)
    with pytest.raises(RustConfigError):
        utils.load_rust_module(tmp_path / "whatever.so", "whatever")


if __name__ == "__main__":
    test_rust_dependency()
