import platform
from typing import Annotated

import pytest

from xenoform_rs import rust

# the library is built with cc and ar, and named for linux. Remove once build_libs supports macos and windows
if platform.system() != "Linux":
    pytest.skip("skipping linux-only tests", allow_module_level=True)


# test can link to local (static) library
@rust(py=False, link_search=["src/test"], link_libs=["static=static"])
def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty: ignore[empty-body]
    """
    unsafe extern "C" {
        fn fibonacci(n: u64) -> u64;
    }
    Ok(unsafe { fibonacci(n) })
    """


def test_local_static_library(build_libs: None) -> None:  # noqa: ARG001
    assert fibonacci(10) == 55
    assert fibonacci(20) == fibonacci(18) + fibonacci(19) == 6765
