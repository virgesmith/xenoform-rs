import inspect
import logging
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable
from functools import cache, lru_cache, wraps
from pathlib import Path
from types import ModuleType
from typing import ParamSpec, TypeVar

from xenoform_rs.config import get_config
from xenoform_rs.errors import AnnotationError, CompilationError, RustConfigError
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import get_function_scope, get_lib_path, load_rust_module, translate_function_signature

logger = logging.getLogger(__name__)


extmodule_root = get_config().extmodule_root

# ensure the module directory is available to Python
sys.path.append(str(extmodule_root))

_module_registry: dict[str, ModuleSpec] = defaultdict(ModuleSpec)


def _get_cargo_env() -> dict[str, str]:
    # Environment variables for linking, especially for macOS.
    # - `undefined dynamic_lookup` is crucial for PyO3 on macOS when building `cdylib`.
    # - `rpath $ORIGIN` (Linux) helps the loader find dependent libraries if any, relative to the executable.
    #   (Though less critical for single shared lib, good practice).
    # Note: For Windows, this might not be needed or might need different flags.
    # Best to run with default first and add if issues.
    cargo_env = os.environ.copy()
    match sys.platform:
        case "darwin":
            cargo_env["RUSTFLAGS"] = (
                cargo_env.get("RUSTFLAGS", "") + " -C link-arg=-undefined -C link-arg=dynamic_lookup"
            )
        case "linux":
            cargo_env["RUSTFLAGS"] = cargo_env.get("RUSTFLAGS", "") + " -C link-arg=-Wl,-rpath,$ORIGIN"
    return cargo_env


_CHECKSUM_SCRIPT = """
import sys
import importlib.util
from importlib.machinery import ExtensionFileLoader
loader = ExtensionFileLoader("{module_name}", "{module_path}")
spec = importlib.util.spec_from_loader("{module_name}", loader)
module = importlib.util.module_from_spec(spec)
sys.modules["{module_name}"] = module
spec.loader.exec_module(module)
print(module.__checksum__)
    """


# need to load module in a subprocess to check its up-to-date to avoid polluting sys.modules
# otherwise if a rebuild is done, the module is already loaded and the changes are not picked up
# importlib.reload doesn't work here, the old module remains in memory
def _get_module_checksum(module_path: Path, module_name: str) -> str | None:
    p = subprocess.run(
        ["python", "-c", _CHECKSUM_SCRIPT.format(module_path=module_path, module_name=module_name)],
        check=False,
        capture_output=True,
        text=True,
    )
    if p.returncode == 0:
        return p.stdout.strip()
    return None


P = ParamSpec("P")
R = TypeVar("R")


def _check_annotations[**P, R](func: Callable[P, R]) -> None:
    """Ensures all args and return are typed"""
    sig = inspect.signature(func)

    missing_annotations = ", ".join(
        param for param, type_ in sig.parameters.items() if type_.annotation is inspect.Parameter.empty
    )
    if sig.return_annotation is inspect.Parameter.empty:
        missing_annotations += ", (return)"

    if missing_annotations:
        raise AnnotationError(f"Function {func.__name__} has missing annotations: {missing_annotations}")  # ty:ignore[unresolved-attribute]


def _check_build_fetch_module_impl(
    module_name: str,
    module_spec: ModuleSpec,
) -> ModuleType:
    ext_name = module_name + "_ext"

    module_dir = extmodule_root / ext_name
    module_dir.mkdir(exist_ok=True, parents=True)

    module, code, hashval = module_spec.make_source(module_name)

    lib_path = get_lib_path(module_dir, module_name)

    # if a built module already exists, and matches the hash of the source code, just use it
    module_checksum = _get_module_checksum(lib_path, module_name)

    # assume exists and up-to-date
    exists, outdated = True, False
    if not module_checksum:
        logger.info(f"module {extmodule_root.name}.{ext_name}.{module_name} not found")
        exists = False
    elif module_checksum != hashval:
        logger.info(f"module is outdated ({hashval})")
        outdated = True
    else:
        logger.info(f"module is up-to-date ({hashval})")

    if outdated or not exists:
        logger.info(f"(re)building module {extmodule_root.name}.{ext_name}.{module_name}")

        # save the code with the hash embedded
        src_dir = module_dir / "src"
        src_dir.mkdir(exist_ok=True)
        with (src_dir / "lib.rs").open("w") as fd:
            # can't use format as its full of { }
            fd.write(code.replace("__HASH__", str(hashval)))
        logger.info(f"wrote {module_dir}/lib.rs")

        for file in module_spec.modules:
            dest = src_dir / file.name
            dest.write_bytes(file.read_bytes())
            logger.info(f"copied {file} to {dest}")

        # Write Cargo.toml
        with (module_dir / "Cargo.toml").open("w") as f:
            f.write(module)

        logger.info(f"wrote {module_dir}/Cargo.toml")
        logger.info(f"building {extmodule_root.name}.{ext_name}.{module_name}...")
        try:
            build_log = module_dir / "build.log"

            with build_log.open("w") as fd:
                compile_result = subprocess.run(
                    ["cargo", "build", "--release"],
                    cwd=module_dir,
                    check=True,
                    stdout=fd,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=_get_cargo_env(),
                )
            if compile_result.returncode != 0:
                raise CompilationError(
                    f"Cargo build failed for module '{ext_name}' with return code {compile_result.returncode}. See {build_log} for details."
                )
        except subprocess.CalledProcessError as e:
            raise RustConfigError(
                f"Cargo build command error while building '{ext_name}'. See {build_log} for details."
            ) from e

        logger.info(f"built {extmodule_root.name}.{ext_name}.{module_name}")

    if not lib_path.exists():
        raise RustConfigError(
            f"Compiled library not found at expected path: {lib_path}\n"
            f"Check cargo output for build errors or different naming conventions."
        )

    return load_rust_module(lib_path, module_name)


@cache  # unlimited module cache
def _get_module(module_name: str) -> ModuleType:
    module = _check_build_fetch_module_impl(module_name, _module_registry[module_name])
    logger.info(f"imported compiled module {module.__name__}")
    return module


@lru_cache  # limited function cache
def _get_function(module_name: str, function_name: str) -> Callable[P, R]:
    module = _get_module(module_name)
    logger.info(f"redirected {function_name[1:]} to compiled function {module.__name__}.{function_name}")
    # return cast(Callable[P, R], getattr(module, function_name))
    return getattr(module, function_name)


def rust(
    *,
    py: bool = True,
    dependencies: list[str] | None = None,
    modules: list[str | Path] | None = None,
    imports: list[str] | None = None,
    module_name: str | None = None,
    profile: dict[str, str] | None = None,
    edition: str | None = None,
    help: str | None = None,
    verbose: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory for compiling rust function implementations into extension modules.

    Returns:
        Callable[..., Callable[..., Any]]: A function that when called, will return the compiled function.
    """

    if verbose:
        logging.basicConfig(
            format="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s", level=logging.INFO, datefmt="%H:%M:%S"
        )

    else:
        logging.basicConfig(level=logging.WARNING)

    def register_function(func: Callable[P, R]) -> Callable[P, R]:
        """Decorator to compile a Python function to Rust and replace it with the compiled version."""

        scope = get_function_scope(func)

        _check_annotations(func)

        sig, args = translate_function_signature(func, py=py)

        nonlocal module_name
        module_name = module_name or f"{Path(inspect.getfile(func)).stem}"
        if not module_name.isidentifier():
            raise RustConfigError(f"Invalid module name: {module_name}. Use only alphanumeric characters and '_'")

        function_body = sig + " {" + (func.__doc__ or "") + "}"

        logger.info(f"registering {module_name}_ext.{module_name}.{func.__name__} (in {extmodule_root})")  # ty:ignore[unresolved-attribute]

        arg_defs = ", ".join(args)

        # overwrite the python stub's docstr...
        if help:
            func.__doc__ = help

        # ...as well as adding the help to the ext module
        function_spec = FunctionSpec(
            name=func.__name__,  # ty:ignore[unresolved-attribute]
            py=py,
            body=function_body,
            arg_annotations=arg_defs,
            scope=scope,
            help=help,
        )

        _module_registry[module_name].add_function(
            function_spec,
            deps=dependencies or [],
            uses=imports or [],
            edition=edition,
            profile=profile or {},
            modules=[Path(m) for m in modules or []],
        )

        @wraps(func)
        def call_function(*args: P.args, **kwargs: P.kwargs) -> R:
            """Compilation is deferred until here (and cached)"""
            rust_fn = _get_function(module_name, function_spec.qualified_name())
            return rust_fn(*args, **kwargs)

        return call_function

    return register_function
