import sys
from pathlib import Path

import pytest

from xenoform_rs import NUMPY, RustConfigError, rust_dependency, utils
from xenoform_rs.config import get_config
from xenoform_rs.errors import RustModuleError


def test_rust_dependency() -> None:
    assert rust_dependency("num", "*") == 'num = "*"'
    assert f'numpy = {{ version = "{get_config().pyo3_version}" }}' == NUMPY
    assert (
        rust_dependency("pyo3", version="0.29", features=["extension-module", "abi3-py313"])
        == """pyo3 = { version = "0.29", features = ['extension-module', 'abi3-py313'] }"""
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
    extmodule_root = Path("/some/ext")
    release = extmodule_root / "target" / utils.python_abi_tag() / "release"

    monkeypatch.setattr(sys, "platform", "darwin")
    assert utils.get_lib_path(extmodule_root, "mod") == release / "libmod.dylib"

    monkeypatch.setattr(sys, "platform", "win32")
    assert utils.get_lib_path(extmodule_root, "mod") == release / "mod.dll"

    monkeypatch.setattr(sys, "platform", "sunos5")
    with pytest.raises(RustConfigError):
        utils.get_lib_path(extmodule_root, "mod")


def test_load_rust_module_invalid_lib(tmp_path: Path) -> None:
    junk = tmp_path / "junk_lib.so"
    junk.write_bytes(b"not a shared library")
    with pytest.raises(RustModuleError):
        utils.load_rust_module(junk, "junk_lib")


def test_load_rust_module_no_spec(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(utils, "spec_from_loader", lambda *_args, **_kwargs: None)
    with pytest.raises(RustConfigError):
        utils.load_rust_module(tmp_path / "whatever.so", "whatever")


def test_write_utf8(tmp_path: Path) -> None:
    path = tmp_path / "lib.rs"
    utils.write_utf8(path, "old")
    utils.write_utf8(path, "fn f() {}\n// ü\n")

    # UTF-8 with LF line endings on every platform, not the locale encoding with CRLF on windows
    assert path.read_bytes() == "fn f() {}\n// ü\n".encode()


def test_write_utf8_same_content_is_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "lib.rs"
    utils.write_utf8(path, "fn f() {}\n")

    def fail(*_args: object) -> None:
        raise AssertionError("file was rewritten")

    # a rewrite would update the mtime, so cargo would rebuild
    monkeypatch.setattr(Path, "write_bytes", fail)
    utils.write_utf8(path, "fn f() {}\n")

    assert path.read_bytes() == b"fn f() {}\n"


if __name__ == "__main__":
    test_rust_dependency()
