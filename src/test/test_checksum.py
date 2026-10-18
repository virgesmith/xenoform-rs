import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from xenoform_rs import CompilationError, RustConfigError
from xenoform_rs import compile as compile_mod
from xenoform_rs.compile import _check_build_fetch_module_impl
from xenoform_rs.config import get_config
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import get_checksum_path, get_lib_path


def _spec(body: str = "Ok(42)") -> ModuleSpec:
    return ModuleSpec().add_function(
        FunctionSpec(name="answer", py=False, body=f"() -> PyResult<i32> {{{body}}}", arg_annotations="", scope=())
    )


def _checksum_path(module_name: str) -> Path:
    return get_checksum_path(get_lib_path(get_config().extmodule_root, module_name))


def _hash(module_name: str, spec: ModuleSpec) -> str:
    return spec.make_source(module_name)[2]


@pytest.fixture(autouse=True)
def no_load(monkeypatch: pytest.MonkeyPatch) -> None:
    # these tests are about when cargo runs, not the loaded module. Not loading also means a module can be rebuilt
    # within the test, which windows would refuse once its DLL was loaded
    monkeypatch.setattr(compile_mod, "load_rust_module", lambda _lib_path, module_name: ModuleType(module_name))


@pytest.fixture
def cargo_runs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    runs: list[list[str]] = []
    real_run = subprocess.run

    def spy(args: list[str], *rest: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[0] == "cargo":
            runs.append(args)
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    return runs


def test_build_writes_checksum_and_reuses_module(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _checksum_path("checksum_reuse").unlink(missing_ok=True)

    _check_build_fetch_module_impl("checksum_reuse", spec)
    assert len(cargo_runs) == 1
    assert _checksum_path("checksum_reuse").read_text(encoding="utf-8") == _hash("checksum_reuse", spec)

    # the sidecar matches the sources, so the existing build is reused
    _check_build_fetch_module_impl("checksum_reuse", spec)
    assert len(cargo_runs) == 1


def test_missing_checksum_rebuilds(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_missing", spec)
    # e.g. an ext folder built before sidecars existed
    _checksum_path("checksum_missing").unlink()
    cargo_runs.clear()

    _check_build_fetch_module_impl("checksum_missing", spec)
    assert len(cargo_runs) == 1
    assert _checksum_path("checksum_missing").exists()


def test_stale_checksum_rebuilds(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_stale", spec)
    # as if the sources had changed since the last build
    _checksum_path("checksum_stale").write_text("0" * 64, encoding="utf-8")
    cargo_runs.clear()

    _check_build_fetch_module_impl("checksum_stale", spec)
    assert len(cargo_runs) == 1
    assert _checksum_path("checksum_stale").read_text(encoding="utf-8") == _hash("checksum_stale", spec)


def test_checksum_without_library_rebuilds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cargo_runs: list[list[str]]
) -> None:
    spec = _spec()
    lib_path = tmp_path / "libchecksum_no_lib.so"
    monkeypatch.setattr(compile_mod, "get_lib_path", lambda _extmodule_root, _module_name: lib_path)
    get_checksum_path(lib_path).write_text(_hash("checksum_no_lib", spec), encoding="utf-8")

    # a matching sidecar isn't trusted without the library. cargo builds elsewhere, so it's still missing afterwards
    with pytest.raises(RustConfigError, match="Compiled library not found"):
        _check_build_fetch_module_impl("checksum_no_lib", spec)
    assert len(cargo_runs) == 1
    assert not get_checksum_path(lib_path).exists()


def test_failed_build_leaves_no_checksum() -> None:
    _check_build_fetch_module_impl("checksum_failed", _spec())
    assert _checksum_path("checksum_failed").exists()

    # a rebuild removes the old checksum before cargo runs, so a build that doesn't complete leaves none behind to vouch
    # for whatever binary is left in the target dir
    with pytest.raises(CompilationError):
        _check_build_fetch_module_impl("checksum_failed", _spec("Ok(not_defined)"))
    assert not _checksum_path("checksum_failed").exists()
