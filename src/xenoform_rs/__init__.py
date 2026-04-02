import subprocess
from importlib import metadata

__version__ = metadata.version("xenoform-rs")

from .compile import rust
from .errors import AnnotationError, CompilationError, RustConfigError, RustTypeError, XenoformRsError
from .utils import rust_dependency


def _check_rust_installed() -> None:
    """Check rust is available"""
    try:
        subprocess.run(["rustc", "--version"], check=True, capture_output=True)
    except Exception as e:
        raise ImportError(
            "xenoform-rs requires rust to be installed on the host machine. See https://rust-lang.org/tools/install/"
        ) from e


_check_rust_installed()


__all__ = [
    "AnnotationError",
    "CompilationError",
    "RustConfigError",
    "RustTypeError",
    "XenoformRsError",
    "__version__",
    "rust",
    "rust_dependency",
]
