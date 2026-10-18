import inspect
import json
import logging
import os
import re
import subprocess
import sys
import warnings
from collections import ChainMap, defaultdict
from collections.abc import Callable, Mapping
from functools import lru_cache, wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from xenoform_rs.config import get_config
from xenoform_rs.errors import (
    AnnotationError,
    CompilationError,
    RustConfigError,
    RustDiagnostic,
    RustTypeError,
    RustWarning,
)
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import (
    get_checksum_path,
    get_function_scope,
    get_lib_path,
    get_target_dir,
    load_rust_module,
    translate_constant,
    translate_function_signature,
)

logger = logging.getLogger(__name__)


def _configure_verbose_logging() -> None:
    """Turn on INFO-level logging for this library's own logger.

    Deliberately does not touch `logging.basicConfig`/the root logger - doing so would
    clobber whatever logging configuration the host application has already set up.
    Instead this gives our namespaced logger its own level and handler and stops it
    propagating to the root logger, so it's fully isolated from - and never interferes
    with - the host's config either way.
    """
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.propagate = False


extmodule_root = get_config().extmodule_root

_module_registry: dict[str, ModuleSpec] = defaultdict(ModuleSpec)

_RUST_KEYWORDS = frozenset(
    {
        "as",
        "break",
        "const",
        "continue",
        "crate",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "unsafe",
        "use",
        "where",
        "while",
        "async",
        "await",
        "dyn",
        "abstract",
        "become",
        "box",
        "do",
        "final",
        "macro",
        "override",
        "priv",
        "typeof",
        "unsized",
        "virtual",
        "yield",
        "try",
    }
)


def _get_cargo_env() -> dict[str, str]:
    # Environment variables for linking, especially for macOS.
    # - `undefined dynamic_lookup` is crucial for PyO3 on macOS when building `cdylib`.
    # - `rpath $ORIGIN` (Linux) helps the loader find dependent libraries if any, relative to the executable.
    #   (Though less critical for single shared lib, good practice).
    # Note: For Windows, this might not be needed or might need different flags.
    # Best to run with default first and add if issues.
    cargo_env = os.environ.copy()
    # Build into the shared, ABI-specific target dir and pin pyo3 to the running interpreter. Together these ensure a
    # binary is built for — and only reused by — the exact interpreter that will load it: PYO3_PYTHON stops
    # pyo3 configuring against an unrelated `python` on PATH, and the per-ABI target dir stops a GIL->free-threaded
    # switch (which keeps the same venv path, so cargo's fingerprint is unchanged) reusing a stale build.
    # absolute: cargo runs with cwd=module_dir, so a relative CARGO_TARGET_DIR would resolve against that
    cargo_env["CARGO_TARGET_DIR"] = str(get_target_dir(extmodule_root).resolve())
    cargo_env["PYO3_PYTHON"] = sys.executable
    match sys.platform:
        case "darwin":  # pragma: no cover - platform-specific
            cargo_env["RUSTFLAGS"] = (
                cargo_env.get("RUSTFLAGS", "") + " -C link-arg=-undefined -C link-arg=dynamic_lookup"
            )
        case "linux":
            cargo_env["RUSTFLAGS"] = cargo_env.get("RUSTFLAGS", "") + " -C link-arg=-Wl,-rpath,$ORIGIN"
    return cargo_env


# Read from a sidecar file rather than the module's own __checksum__: that would mean loading the module, and a loaded
# extension can't be unloaded or reloaded, so a rebuild would never be picked up in this process.
def _read_checksum(checksum_path: Path) -> str | None:
    try:
        return checksum_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_cargo_messages(stdout: str) -> list[RustDiagnostic]:
    """Extract the rustc diagnostics (errors and warnings) from cargo's JSON message stream"""
    diagnostics = []
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("reason") != "compiler-message":
            continue
        message = record["message"]
        # some errors (e.g. linker failures) have no source location
        primary = next((s for s in message["spans"] if s["is_primary"]), None)
        diagnostics.append(
            RustDiagnostic(
                level=message["level"],
                code=message["code"]["code"] if message["code"] else None,
                message=message["message"],
                rendered=message["rendered"],
                file=primary["file_name"] if primary else None,
                line=primary["line_start"] if primary else None,
                has_suggestion=any(
                    span["suggested_replacement"] is not None
                    for child in message["children"]
                    for span in child["spans"]
                ),
            )
        )
    return diagnostics


def _select(errors: list[RustDiagnostic]) -> list[RustDiagnostic]:
    """
    The errors worth showing inline: those with a suggested fix, or failing that the first. Errors are often knock-on
    effects of another, and the one carrying a fix is usually the root cause
    """
    return [e for e in errors if e.has_suggestion] or errors[:1]


_SOURCE_LOCATION = re.compile(r"^\s*(?:-->|:::) (.+):\d+:\d+$")
_SECTION_HEADER = re.compile(r"^[a-z-]+(?:\[\w+\])?: ")
# an inline "= help:" followed by lines indented beyond its "=", e.g. a list of every type implementing a trait
_HELP_LIST = re.compile(r"^( *)= help: .*\n(?:\1 .+\n?)+", re.MULTILINE)


def _brief(rendered: str) -> str:
    """
    Shorten rustc's rendered output by dropping multi-line "= help:" lists and the sub-diagnostics that point outside
    the crate (e.g. into std or dependency sources), keeping those - such as suggested fixes - that refer to the
    generated code
    """
    # a sub-diagnostic starts with a header like "help: ..." - indentation can't be used to detect them because
    # line numbers as wide as the gutter (e.g. "562 | ...") also start at column 0
    sections: list[list[str]] = []
    for line in _HELP_LIST.sub("", rendered).rstrip().splitlines():
        if not sections or _SECTION_HEADER.match(line):
            sections.append([])
        sections[-1].append(line)

    # crate paths are relative; external ones are rooted but not necessarily absolute - without the rust-src component
    # std is reported as "/rustc/<hash>/library/...", which has no drive so isn't absolute on Windows
    def is_external(section: list[str]) -> bool:
        return any((m := _SOURCE_LOCATION.match(line)) and Path(m[1]).anchor for line in section)

    head, *rest = sections
    return "\n".join(line for section in [head, *(s for s in rest if not is_external(s))] for line in section)


def _warn(ext_name: str, diagnostics: list[RustDiagnostic]) -> None:
    """Issue a RustWarning for each warning in a successful build"""
    for d in diagnostics:
        if d.level == "warning":
            # attribute to the user code whose call triggered the build, not to this library
            warnings.warn(
                RustWarning(f"rustc warning in module '{ext_name}':\n{_brief(d.rendered)}", d),
                skip_file_prefixes=(str(Path(__file__).parent),),
            )


def _stderr_errors(stderr: str) -> str:
    """Cargo's own error output, without the preceding progress lines"""
    lines = stderr.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("error")), max(len(lines) - 20, 0))
    return "\n".join(lines[start:])


def _check_annotations[**P, R](func: Callable[P, R]) -> None:
    """Ensures all args and return are typed"""
    sig = inspect.signature(func)

    missing_annotations = [
        param for param, type_ in sig.parameters.items() if type_.annotation is inspect.Parameter.empty
    ]
    if sig.return_annotation is inspect.Parameter.empty:
        missing_annotations.append("(return)")

    if missing_annotations:
        raise AnnotationError(f"Function {func.__name__} has missing annotations: {', '.join(missing_annotations)}")  # ty:ignore[unresolved-attribute]


def _validate_signature[**P, R](func: Callable[P, R], py: bool) -> tuple[str, list[str]]:
    """Validate annotations and translate to Rust signature, aggregating all errors before raising."""
    annotation_err: str | None = None
    type_err: RustTypeError | None = None

    try:
        _check_annotations(func)
    except AnnotationError as e:
        annotation_err = str(e)

    try:
        sig, args = translate_function_signature(func, py=py)
    except RustTypeError as e:
        type_err = e
        sig, args = "", []

    if annotation_err and type_err:
        raise AnnotationError(f"{annotation_err}\n{type_err}")
    if annotation_err:
        raise AnnotationError(annotation_err)
    if type_err:
        raise type_err
    return sig, args


def _validate_module_name(module_name: str) -> None:
    if not module_name.isidentifier():
        raise RustConfigError(f"Invalid module name: '{module_name}'. Use only alphanumeric characters and '_'")
    if module_name in _RUST_KEYWORDS:
        raise RustConfigError(
            f"Invalid module name: '{module_name}' is a Rust reserved word, "
            "override with module_name=... in the rust decorator"
        )


def _parse_constant(entry: str) -> tuple[str, str | None]:
    """Split a `constants` entry, "NAME" or "NAME: rust_type", into its name and optional rust type"""
    name, colon, rust_type = (part.strip() for part in entry.partition(":"))
    if not name.isidentifier() or name in _RUST_KEYWORDS:
        raise RustConfigError(
            f"Invalid constant name: '{name}'. Use a valid identifier that isn't a Rust reserved word"
        )
    if colon and not rust_type:
        raise RustConfigError(f"Missing rust type for constant '{name}'. Use e.g. '{name}: u64', or just '{name}'")
    return name, rust_type or None


def _translate_constants(entries: list[str], namespace: Mapping[str, Any]) -> list[str]:
    """
    Translate constants to rust const items, looking each value up by name in the namespace. The type is given in the
    entry, not read from any annotation on the python variable: an annotation belongs to the module that declares it,
    so it's lost when the constant is imported, and the type would silently fall back to the default
    """
    constant_defs = []
    for entry in entries:
        name, rust_type = _parse_constant(entry)
        if name not in namespace:
            raise RustConfigError(f"Constant '{name}' not found in the scope the function is defined in")
        constant_defs.append(translate_constant(name, namespace[name], rust_type))
    return constant_defs


def _check_build_fetch_module_impl(
    module_name: str,
    module_spec: ModuleSpec,
) -> ModuleType:
    ext_name = module_name + "_ext"

    module_dir = extmodule_root / ext_name
    module_dir.mkdir(exist_ok=True, parents=True)

    if str(extmodule_root) not in sys.path:
        sys.path.append(str(extmodule_root))

    module, code, hashval = module_spec.make_source(module_name)

    lib_path = get_lib_path(extmodule_root, module_name)
    checksum_path = get_checksum_path(lib_path)

    # if a built module already exists, and matches the hash of the source code, just use it
    module_checksum = _read_checksum(checksum_path) if lib_path.exists() else None

    # assume exists and up-to-date
    exists, outdated = True, False
    if module_checksum is None:
        logger.info(f"module {extmodule_root.name}.{ext_name}.{module_name} not found or has no checksum")
        exists = False
    elif module_checksum != hashval:
        logger.info(f"module is outdated ({hashval})")
        outdated = True
    else:
        logger.info(f"module is up-to-date ({hashval})")

    if outdated or not exists:
        logger.info(f"(re)building module {extmodule_root.name}.{ext_name}.{module_name}")

        # invalidate before building, and only restore after a successful build: otherwise a failed or interrupted
        # build could leave the old checksum vouching for a binary that wasn't built from these sources
        checksum_path.unlink(missing_ok=True)

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
        build_log = module_dir / "build.log"

        compile_result = subprocess.run(
            ["cargo", "build", "--release", "--message-format=json"],
            cwd=module_dir,
            check=False,
            capture_output=True,
            # rustc emits UTF-8 regardless of platform; the locale default (e.g. cp1252 on Windows) could fail to decode
            encoding="utf-8",
            errors="replace",
            env=_get_cargo_env(),
            timeout=300,
        )
        all_diagnostics = _parse_cargo_messages(compile_result.stdout)
        build_log.write_text(
            compile_result.stderr + "".join(d.rendered for d in all_diagnostics),
            encoding="utf-8",
        )
        if compile_result.returncode != 0:
            errors = [d for d in all_diagnostics if d.level.startswith("error")]
            if errors:
                shown = _select(errors)
                details = "\n\n".join(_brief(d.rendered) for d in shown)
                if hidden := len(errors) - len(shown):
                    details += f"\n\n...and {hidden} more error{'s' if hidden > 1 else ''}, see {build_log}"
            else:
                # errors that never reach rustc (e.g. an invalid Cargo.toml) are only reported on stderr
                details = _stderr_errors(compile_result.stderr)
            raise CompilationError(
                f"Cargo build failed for module '{ext_name}' (full output in {build_log}):\n\n{details}",
                errors,
            )

        if not lib_path.exists():
            raise RustConfigError(
                f"Compiled library not found at expected path: {lib_path}\n"
                f"Check cargo output for build errors or different naming conventions."
            )

        checksum_path.write_text(hashval, encoding="utf-8")
        _warn(ext_name, all_diagnostics)
        logger.info(f"built {extmodule_root.name}.{ext_name}.{module_name}")

    # namespaced, as module_name defaults to the defining python module's name, which a bare sys.modules entry would
    # replace (breaking any later import of it). The init function is found from the last component of the name
    return load_rust_module(lib_path, f"{ext_name}.{module_name}")


@lru_cache(maxsize=256)
def _get_module(module_name: str) -> ModuleType:
    module = _check_build_fetch_module_impl(module_name, _module_registry[module_name])
    logger.info(f"imported compiled module {module.__name__}")
    return module


@lru_cache(maxsize=256)
def _get_function(module_name: str, function_name: str) -> Callable[..., Any]:
    module = _get_module(module_name)
    logger.info(f"redirected {function_name[1:]} to compiled function {module.__name__}.{function_name}")
    return getattr(module, function_name)


def rust[**P, R](
    *,
    py: bool = True,
    dependencies: list[str] | None = None,
    modules: list[str | Path] | None = None,
    imports: list[str] | None = None,
    module_name: str | None = None,
    profile: dict[str, str] | None = None,
    edition: str | None = None,
    help: str | None = None,
    constants: list[str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory for compiling rust function implementations into extension modules.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: A decorator that replaces the function with its compiled
        version, preserving its signature.
    """

    if get_config().verbose is not None:
        _configure_verbose_logging()

    def register_function(func: Callable[P, R]) -> Callable[P, R]:
        """Decorator to compile a Python function to Rust and replace it with the compiled version."""

        scope = get_function_scope(func)
        sig, args = _validate_signature(func, py=py)

        nonlocal module_name
        module_name = module_name or f"{Path(inspect.getfile(func)).stem}"
        _validate_module_name(module_name)

        # the caller is the scope the decorator is applied in, so its locals cover class bodies and functions, and its
        # globals cover module-level and imported names
        caller = sys._getframe(1)
        constant_defs = _translate_constants(constants or [], ChainMap(caller.f_locals, caller.f_globals))

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
            constants=constant_defs,
        )

        @wraps(func)
        def call_function(*args: P.args, **kwargs: P.kwargs) -> R:
            """Compilation is deferred until here (and cached)"""
            rust_fn = _get_function(module_name, function_spec.qualified_name())
            return rust_fn(*args, **kwargs)

        return call_function

    return register_function
