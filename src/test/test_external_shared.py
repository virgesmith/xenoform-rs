import platform
from pathlib import Path
from typing import Annotated

import pytest

from xenoform_rs import rust

# the library is built with cc, and named and found (via rpath) for linux. Remove once build_libs supports macos and
# windows
if platform.system() != "Linux":
    pytest.skip("skipping linux-only tests", allow_module_level=True)


# test can link to local shared library. The rpath lets the loader find it when the module is imported
@rust(
    py=False,
    link_search=["src/test"],
    link_libs=["dylib=shared"],
    link_args=[f"-Wl,-rpath,{Path('src/test').resolve()}"],
)
def lucas(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty: ignore[empty-body]
    """
    unsafe extern "C" {
        fn lucas(n: u64) -> u64;
    }
    Ok(unsafe { lucas(n) })
    """


def test_local_shared_library(build_libs: None) -> None:  # noqa: ARG001
    # 2, 1, 3, 4, 7, 11, 18, 29, 47, 76, 123
    assert lucas(10) == 123
