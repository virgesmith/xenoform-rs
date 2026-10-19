import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import xenoform_rs
from xenoform_rs import AnnotationError, CompilationError, RustConfigError, RustTypeError, rust
from xenoform_rs import compile as compile_mod
from xenoform_rs.compile import _check_build_fetch_module_impl, _validate_module_name, _validate_signature
from xenoform_rs.config import XenoformRsConfig
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec


def test_check_rust_installed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("rustc not found")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ImportError):
        xenoform_rs._check_rust_installed()


def test_validate_signature_type_error_only() -> None:
    class Unmapped: ...

    def f(_x: Unmapped) -> None:
        ""

    with pytest.raises(RustTypeError):
        _validate_signature(f, py=False)


def test_validate_signature_annotation_error_only() -> None:
    def f(_x) -> None:
        ""

    with pytest.raises(AnnotationError):
        _validate_signature(f, py=False)


def test_validate_signature_combined_errors() -> None:
    class Unmapped: ...

    def f(_x: Unmapped, _y) -> None:
        ""

    with pytest.raises(AnnotationError):
        _validate_signature(f, py=False)


def test_validate_module_name() -> None:
    with pytest.raises(RustConfigError):
        _validate_module_name("not an identifier")
    with pytest.raises(RustConfigError):
        _validate_module_name("fn")


# fibonacci.rs is copied in to cover module copying but not used, so rustc warns of an unused import
@pytest.mark.filterwarnings("ignore::xenoform_rs.RustWarning")
def test_rebuild_when_outdated(monkeypatch: pytest.MonkeyPatch) -> None:
    # force a checksum mismatch so the module is considered stale and rebuilt
    monkeypatch.setattr(compile_mod, "_read_checksum", lambda *_args: "0" * 64)

    @rust(py=False, module_name="outdated_mod", modules=["src/test/fibonacci.rs"])
    def plus_one(x: int) -> int:  # ty: ignore[empty-body]
        """Ok(x + 1)"""

    assert plus_one(1) == 2


@pytest.mark.skipif(
    sys.platform == "win32", reason="re-checking a loaded module rebuilds on windows, which fails on the locked DLL"
)
def test_module_reused_when_up_to_date() -> None:
    body = "() -> PyResult<i32> {Ok(42)}"
    spec = ModuleSpec().add_function(FunctionSpec(name="answer", py=False, body=body, arg_annotations="", scope=()))
    # builds the module if not already present and up-to-date
    module = _check_build_fetch_module_impl("reuse_mod", spec)
    assert module._answer() == 42
    # second check finds the built module up-to-date and reuses it
    module = _check_build_fetch_module_impl("reuse_mod", spec)
    assert module._answer() == 42


def test_compiled_lib_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        compile_mod, "get_lib_path", lambda _extmodule_root, module_name: Path("/nonexistent") / f"lib{module_name}.so"
    )

    @rust(py=False, module_name="lib_missing_mod")
    def noop() -> None:
        """Ok(())"""

    # compilation is deferred until the first call
    with pytest.raises(RustConfigError):
        noop()


def test_build_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # force a rebuild, with a configured timeout, and a cargo that always times out
    monkeypatch.setattr(compile_mod, "_read_checksum", lambda *_args: "0" * 64)
    monkeypatch.setattr(compile_mod, "get_config", lambda: XenoformRsConfig(build_timeout=7))
    real_run = subprocess.run

    def time_out(args: list[str], *rest: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[0] == "cargo":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", time_out)
    spec = ModuleSpec().add_function(
        FunctionSpec(name="f", py=False, body="() -> PyResult<()> {Ok(())}", arg_annotations="", scope=())
    )

    # the configured value reaches cargo, and the error says how to change it
    with pytest.raises(CompilationError, match=r"timed out after 7s.*XENOFORM_RS_BUILD_TIMEOUT"):
        _check_build_fetch_module_impl("timeout_mod", spec)


if __name__ == "__main__":
    test_validate_module_name()
