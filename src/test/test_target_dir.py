from xenoform_rs.compile import _check_build_fetch_module_impl
from xenoform_rs.config import get_config
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import get_lib_path, get_target_dir


def _spec(value: int) -> ModuleSpec:
    body = f"() -> PyResult<i32> {{Ok({value})}}"
    return ModuleSpec().add_function(FunctionSpec(name="value", py=False, body=body, arg_annotations="", scope=()))


def test_modules_share_one_target_dir() -> None:
    """Every module builds into the one target dir under extmodule_root, not a target dir of its own"""
    extmodule_root = get_config().extmodule_root
    release_dir = get_target_dir(extmodule_root) / "release"

    for module_name, value in (("shared_target_a", 1), ("shared_target_b", 2)):
        module = _check_build_fetch_module_impl(module_name, _spec(value))
        assert module._value() == value
        assert get_lib_path(extmodule_root, module_name).parent == release_dir
        assert get_lib_path(extmodule_root, module_name).exists()
        assert not (extmodule_root / f"{module_name}_ext" / "target").exists()
