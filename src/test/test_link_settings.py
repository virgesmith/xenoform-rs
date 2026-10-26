import shlex
from pathlib import Path

from xenoform_rs.compile import _check_build_fetch_module_impl
from xenoform_rs.config import get_config
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec

_FUNCTION = FunctionSpec(name="answer", py=False, body="() -> PyResult<i32> {Ok(42)}", arg_annotations="", scope=())


def test_link_settings_become_rustc_args() -> None:
    spec = ModuleSpec().add_function(
        _FUNCTION, link_search=[Path("/opt/lib")], link_libs=["static=foo"], link_args=["-Wl,-rpath,/opt/lib"]
    )

    assert spec.rustc_args() == [f"-Lnative={Path('/opt/lib')}", "-lstatic=foo", "-Clink-arg=-Wl,-rpath,/opt/lib"]


def test_link_settings_keep_order_and_drop_duplicates() -> None:
    # order matters to the linker, so settings from later functions are appended, not sorted
    spec = (
        ModuleSpec()
        .add_function(_FUNCTION, link_libs=["static=b", "static=a"])
        .add_function(_FUNCTION, link_libs=["static=c", "static=b", "static=c"])
    )

    assert spec.link_libs == ["static=b", "static=a", "static=c"]


def test_link_settings_change_the_hash() -> None:
    def hash_with(libs: list[str]) -> str:
        return ModuleSpec().add_function(_FUNCTION, link_libs=libs).make_source("m")[2]

    assert len({hash_with([]), hash_with(["static=foo"]), hash_with(["static=bar"])}) == 3


def test_link_settings_are_passed_to_rustc_and_logged(tmp_path: Path) -> None:
    # a search path with no libraries in it links nothing, so this builds on every platform. Being a new directory each
    # run, it also changes the hash, so the module is always rebuilt
    spec = ModuleSpec().add_function(_FUNCTION, link_search=[tmp_path])

    module = _check_build_fetch_module_impl("link_settings_passed", spec)

    build_log = get_config().extmodule_root / "link_settings_passed_ext" / "build.log"
    command = build_log.read_text(encoding="utf-8").splitlines()[0]
    assert command == shlex.join(["cargo", "rustc", "--release", "--message-format=json", "--", f"-Lnative={tmp_path}"])
    assert module._answer() == 42
