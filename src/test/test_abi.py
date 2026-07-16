import sys
import sysconfig

import pytest

from xenoform_rs import utils
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec


def _make_spec() -> ModuleSpec:
    return ModuleSpec().add_function(
        FunctionSpec(
            name="identity",
            py=False,
            body="fn _identity(x: i32) -> i32 { x }",
            arg_annotations="x: i32",
            scope=(),
        )
    )


def test_python_abi_reflects_interpreter() -> None:
    abi = utils.python_abi()
    version_tag = f"{sys.version_info.major}{sys.version_info.minor}"
    assert version_tag in abi
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        assert f"{version_tag}t" in abi


def test_python_abi_tag_is_filesystem_safe() -> None:
    tag = utils.python_abi_tag()
    assert tag
    assert all(c.isalnum() or c == "_" for c in tag)


def test_target_dir_isolates_by_abi(monkeypatch: pytest.MonkeyPatch) -> None:
    module_dir = utils.Path("/some/module")
    default = utils.get_target_dir(module_dir)
    assert default == module_dir / "target" / utils.python_abi_tag()

    monkeypatch.setattr(utils, "python_abi", lambda: ".cpython-999t-other.so")
    assert utils.get_target_dir(module_dir) != default


def test_source_is_abi_independent() -> None:
    """The target dir isolates by ABI, so the sources must not: a rebuild under a different interpreter
    must not perturb a source file shared by every ABI."""
    spec = _make_spec()
    _, code, checksum = spec.make_source("abimod")
    assert utils.python_abi() not in code

    _, _, checksum_again = spec.make_source("abimod")
    assert checksum == checksum_again
