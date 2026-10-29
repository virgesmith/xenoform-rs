import subprocess

import pytest


@pytest.fixture(scope="session")
def build_libs() -> None:
    # -fPIC: the static library is linked into the extension module, which is itself a shared library
    cmds = [
        ["cc", "-fPIC", "-c", "test_lib.c", "-o", "test_lib.o"],
        ["ar", "rcs", "libstatic.a", "test_lib.o"],
        ["cc", "-shared", "test_lib.o", "-o", "libshared.so"],
    ]
    for cmd in cmds:
        subprocess.run(cmd, cwd="src/test", check=True, timeout=30)
