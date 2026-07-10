import sys
import sysconfig

import pytest

from xenoform_rs import rustmodule
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
    abi = rustmodule._python_abi()
    version_tag = f"{sys.version_info.major}{sys.version_info.minor}"
    assert version_tag in abi
    if sysconfig.get_config_var("Py_GIL_DISABLED"):
        assert f"{version_tag}t" in abi


def test_abi_embedded_in_source_and_folded_into_checksum(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = _make_spec()
    _, code, checksum = spec.make_source("abimod")
    assert f"// Built for Python ABI: {rustmodule._python_abi()}" in code

    _, _, checksum_again = spec.make_source("abimod")
    assert checksum == checksum_again

    monkeypatch.setattr(rustmodule, "_python_abi", lambda: ".cp999t-other_platform.xyz")
    _, code_other_abi, checksum_other_abi = spec.make_source("abimod")
    assert "// Built for Python ABI: .cp999t-other_platform.xyz" in code_other_abi
    assert checksum_other_abi != checksum
