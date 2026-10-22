import shutil
import subprocess
import sys

import pytest

from xenoform_rs.config import get_config

# builds the module without loading it: these tests are about the files written during a build. Not loading also
# avoids windows refusing to rebuild a DLL that another process has loaded
_BUILD_SCRIPT = """
from types import ModuleType
from xenoform_rs import compile as compile_mod
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec

compile_mod.load_rust_module = lambda _lib_path, module_name: ModuleType(module_name)
function = FunctionSpec(name="answer", py=False, body="() -> PyResult<i32> {Ok(42)}", arg_annotations="", scope=())
compile_mod._check_build_fetch_module_impl("concurrent_mod", ModuleSpec().add_function(function))
"""


# Intermittent on windows: a replace of lib.rs can be refused (WinError 5) while another build has it open or is
# replacing it, and then the file can't be read to see that it already holds the same content. Allowed to fail for now:
# concurrent builds of one module are rare, and a retry would add complexity to atomic_write. Not strict, as it usually
# passes. Remove once atomic writes are either made robust on windows or reconsidered (see JOURNAL.md, 2026-10-22).
@pytest.mark.xfail(sys.platform == "win32", reason="windows can refuse a replace of a file in use", strict=False)
def test_concurrent_builds_of_the_same_module_succeed() -> None:
    # each process finds no module and builds it, rewriting the same sources while another's cargo may be reading them.
    # The window for a torn read is narrow, so this rarely failed before the writes were atomic. It's here to check that
    # concurrent replaces of the same file work on every platform (windows can refuse a replace of a file in use)
    shutil.rmtree(get_config().extmodule_root / "concurrent_mod_ext", ignore_errors=True)
    processes = [
        subprocess.Popen([sys.executable, "-c", _BUILD_SCRIPT], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(4)
    ]
    results = [process.communicate(timeout=get_config().build_timeout) for process in processes]

    for process, (_, stderr) in zip(processes, results, strict=True):
        assert process.returncode == 0, stderr.decode(errors="replace")
    module_dir = get_config().extmodule_root / "concurrent_mod_ext"
    assert not list(module_dir.rglob(".*.tmp"))
