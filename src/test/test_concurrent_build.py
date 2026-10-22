import shutil
import subprocess
import sys

from xenoform_rs.config import get_config
from xenoform_rs.utils import get_checksum_path

# builds the module without loading it: these tests are about the files written during a build. Not loading also
# avoids windows refusing to rebuild a DLL that another process has loaded. The function body is the first argument
_BUILD_SCRIPT = """
import sys
from types import ModuleType
from xenoform_rs import compile as compile_mod
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec

compile_mod.load_rust_module = lambda _lib_path, module_name: ModuleType(module_name)
body = f"() -> PyResult<i32> {{{sys.argv[1]}}}"
function = FunctionSpec(name="answer", py=False, body=body, arg_annotations="", scope=())
compile_mod._check_build_fetch_module_impl("concurrent_mod", ModuleSpec().add_function(function))
"""


def _build_concurrently(*bodies: str) -> None:
    shutil.rmtree(get_config().extmodule_root / "concurrent_mod_ext", ignore_errors=True)
    processes = [
        subprocess.Popen([sys.executable, "-c", _BUILD_SCRIPT, body], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for body in bodies
    ]
    # the builds queue on the lock, so the last may wait for all the others
    results = [process.communicate(timeout=len(bodies) * get_config().build_timeout) for process in processes]

    for process, (_, stderr) in zip(processes, results, strict=True):
        assert process.returncode == 0, stderr.decode(errors="replace")


def test_concurrent_builds_of_the_same_module_succeed() -> None:
    # each process finds no module and tries to build it. Without the lock, one could rewrite the sources while
    # another's cargo was reading them (and on windows, replacing a file another process has open is refused)
    _build_concurrently(*["Ok(42)"] * 4)


def test_concurrent_builds_of_different_sources_stay_consistent() -> None:
    # the builds are serialised, so whichever finishes last leaves its sources, binary and checksum together, rather
    # than one process's checksum vouching for a binary built from the other's source
    _build_concurrently("Ok(42)", "Ok(43)")

    module_dir = get_config().extmodule_root / "concurrent_mod_ext"
    checksum = get_checksum_path(module_dir).read_text(encoding="utf-8")
    assert checksum in (module_dir / "src" / "lib.rs").read_text(encoding="utf-8")
