import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from xenoform_rs import CompilationError, RustConfigError
from xenoform_rs import compile as compile_mod
from xenoform_rs.compile import _check_build_fetch_module_impl
from xenoform_rs.config import get_config
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import get_checksum_path, python_abi_tag, rustfmt


def _spec(body: str = "Ok(42)") -> ModuleSpec:
    return ModuleSpec().add_function(
        FunctionSpec(name="answer", py=False, body=f"() -> PyResult<i32> {{{body}}}", arg_annotations="", scope=())
    )


def _module_dir(module_name: str) -> Path:
    return get_config().extmodule_root / f"{module_name}_ext"


def _checksum_path(module_name: str) -> Path:
    return get_checksum_path(_module_dir(module_name))


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
    # in the module folder, named for the interpreter ABI the binary was built for
    assert _checksum_path("checksum_reuse") == _module_dir("checksum_reuse") / f"{python_abi_tag()}.checksum"
    assert _checksum_path("checksum_reuse").read_text(encoding="utf-8") == _hash("checksum_reuse", spec)

    # the checksum matches the sources, so the existing build is reused
    _check_build_fetch_module_impl("checksum_reuse", spec)
    assert len(cargo_runs) == 1


def test_missing_checksum_rebuilds(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_missing", spec)
    # e.g. an ext folder built before checksum files existed
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


def test_other_abi_checksum_is_ignored(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_other_abi", spec)
    # as if the module had only been built by another interpreter, e.g. 3.14t when running 3.14
    _checksum_path("checksum_other_abi").rename(_module_dir("checksum_other_abi") / "other_abi.checksum")
    cargo_runs.clear()

    _check_build_fetch_module_impl("checksum_other_abi", spec)
    assert len(cargo_runs) == 1


def test_deleted_module_folder_rebuilds(cargo_runs: list[list[str]]) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_no_folder", spec)
    shutil.rmtree(_module_dir("checksum_no_folder"))
    cargo_runs.clear()

    # the binary is untouched in the shared target dir, but the checksum went with the folder
    _check_build_fetch_module_impl("checksum_no_folder", spec)
    assert len(cargo_runs) == 1
    assert (_module_dir("checksum_no_folder") / "src" / "lib.rs").exists()


def test_binary_and_checksum_are_enough_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_lean", spec)
    # e.g. a lean docker image: no generated sources, Cargo files or build log, no rust toolchain (so no subprocesses:
    # neither cargo nor rustfmt), on a read-only filesystem
    for path in _module_dir("checksum_lean").iterdir():
        if path != _checksum_path("checksum_lean"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()

    real_open = Path.open

    def read_only(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only filesystem")

    def open_for_reading(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if set(mode) & set("wax+"):
            read_only()
        return real_open(path, mode, *args, **kwargs)

    def not_installed(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("no rust toolchain")

    for method in ("mkdir", "write_text", "write_bytes", "unlink"):
        monkeypatch.setattr(Path, method, read_only)
    monkeypatch.setattr(Path, "open", open_for_reading)
    monkeypatch.setattr(subprocess, "run", not_installed)

    _check_build_fetch_module_impl("checksum_lean", spec)


def test_generated_source_is_still_formatted() -> None:
    _checksum_path("checksum_formatted").unlink(missing_ok=True)
    _check_build_fetch_module_impl("checksum_formatted", _spec())

    lib_rs = (_module_dir("checksum_formatted") / "src" / "lib.rs").read_text(encoding="utf-8")
    assert rustfmt(lib_rs) == lib_rs


def test_checksum_without_library_rebuilds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cargo_runs: list[list[str]]
) -> None:
    spec = _spec()
    _check_build_fetch_module_impl("checksum_no_lib", spec)
    monkeypatch.setattr(compile_mod, "get_lib_path", lambda _extmodule_root, _module_name: tmp_path / "missing.so")
    cargo_runs.clear()

    # a matching checksum isn't trusted without the library. cargo builds elsewhere, so it's still missing afterwards
    with pytest.raises(RustConfigError, match="Compiled library not found"):
        _check_build_fetch_module_impl("checksum_no_lib", spec)
    assert len(cargo_runs) == 1
    assert not _checksum_path("checksum_no_lib").exists()


def test_failed_build_leaves_no_checksum() -> None:
    _check_build_fetch_module_impl("checksum_failed", _spec())
    assert _checksum_path("checksum_failed").exists()

    # a rebuild removes the old checksum before cargo runs, so a build that doesn't complete leaves none behind to vouch
    # for whatever binary is left in the target dir
    with pytest.raises(CompilationError):
        _check_build_fetch_module_impl("checksum_failed", _spec("Ok(not_defined)"))
    assert not _checksum_path("checksum_failed").exists()


_HASH_SCRIPT = """
import sys
from pathlib import Path
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
function = FunctionSpec(name="f", py=False, body="() -> PyResult<i32> {Ok(1)}", arg_annotations="", scope=())
spec = ModuleSpec().add_function(
    function,
    deps=[f'dep{i} = "1"' for i in range(8)],
    uses=[f"std::collections::Type{i}" for i in range(8)],
    modules=[Path(p) for p in sys.argv[1:]],
)
print(spec.make_source("m")[2])
"""


def test_hash_is_the_same_in_every_process(tmp_path: Path) -> None:
    modules = []
    for i in range(8):
        module = tmp_path / f"mod{i}.rs"
        module.write_text(f"pub fn f{i}() {{}}", encoding="utf-8")
        modules.append(str(module))

    # deps, uses and modules are held in sets, whose order changes with python's per-process string hashing
    hashes = {
        subprocess.run(
            [sys.executable, "-c", _HASH_SCRIPT, *modules],
            env=os.environ | {"PYTHONHASHSEED": str(seed)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in range(3)
    }
    assert len(hashes) == 1
