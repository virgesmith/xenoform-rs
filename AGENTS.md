# AGENTS.md

Guidance for AI coding agents working in the `xenoform-rs` repository.

## What this project is

`xenoform-rs` lets you write and execute Rust inline within Python code. You
write a type-annotated Python function (or method), apply the `@rust` decorator,
and put the Rust implementation in the docstring. On import, xenoform-rs
generates Rust source from the Python signature, compiles a `pyo3` extension
module, and swaps the decorated Python function for its compiled Rust
counterpart. Compiled artifacts are cached and rebuilt only when the source or
`Cargo.toml` hash changes.

It is the Rust sister of the C++ project [xenoform](https://pypi.org/project/xenoform/).

## Requirements

- Python >= 3.12 (3.12, 3.13, 3.14, and free-threaded 3.14t are tested in CI).
- A working Rust toolchain (`rustc`/`cargo` on `PATH`) — `xenoform_rs` raises an
  `ImportError` on import if `rustc` is not found.
- [`uv`](https://docs.astral.sh/uv/) for dependency management and running tasks.

## Setup and common commands

This project uses `uv`. Mirror what CI does in `.github/workflows/lint-test.yml`:

```sh
uv sync --dev --all-extras   # install dev + examples dependencies
uv run ruff check            # lint
uv run ty check              # type check
uv run pytest -sv            # run the test suite
uv run examples/loop.py      # run an example
uv run examples/distance_matrix.py
```

Pre-commit hooks (`uv-lock`, `ruff-check --fix`, `ruff-format`, `ty`) are
configured in `.pre-commit-config.yaml`. Install them with `uv run pre-commit
install` and/or run `uv run pre-commit run --all-files` before pushing.

## Project layout

- `src/xenoform_rs/` — the package source:
  - `compile.py` — the `@rust` decorator factory and the build/registry/redirect
    machinery; the heart of the package.
  - `extension_types.py` — the Python-to-Rust type mapping (`DEFAULT_TYPE_MAPPING`)
    and `translate_type`, including `Annotated` overrides.
  - `rustmodule.py` — `FunctionSpec`/`ModuleSpec` dataclasses and the
    `Cargo.toml` / `lib.rs` templates; computes source hashes for change detection.
  - `utils.py` — signature translation, module loading, `rust_dependency`, helpers.
  - `config.py` — `XenoformConfig` (pydantic-settings), driven by `XENOFORM_RS_*`
    environment variables.
  - `errors.py` — the exception hierarchy rooted at `XenoformRsError`.
- `src/test/` — the pytest suite. Tests are organised by feature
  (`test_numpy.py`, `test_callable.py`, `test_kwargs.py`, `test_slice.py`, etc.)
  and exercise real compilation, so they require a Rust toolchain.
- `examples/` — runnable performance comparison examples.
- `README.md` — the authoritative user-facing documentation; keep it in sync with
  behaviour changes.

## Conventions

- Lint/format with `ruff` (line length 120; rule set defined in `pyproject.toml`).
  Public functions are expected to have docstrings (`D103`), except in
  `src/test/*`.
- Type-check with `ty`. When a deliberate violation is needed, use a targeted
  `# ty: ignore[...]` comment (e.g. `empty-body` on `@rust` functions whose body
  lives in the docstring).
- Raise the project's own exceptions (`AnnotationError`, `CompilationError`,
  `RustConfigError`, `RustTypeError`, `RustModuleError`) rather than bare
  built-ins where a domain error applies.
- The public API is whatever `src/xenoform_rs/__init__.py` exports via `__all__`
  (`rust`, `rust_dependency`, the error types, `__version__`). Update `__all__`
  when adding public symbols.

## Things to know before changing behaviour

- The `pyo3` version is pinned (currently `0.28`) via `XENOFORM_RS_PYO3_VERSION`;
  other versions are not guaranteed to work and generally need type overrides.
- Generated Rust goes to an `ext/` subdirectory by default (overridable with
  `XENOFORM_RS_EXTMODULE_ROOT`). Build output is redirected to `build.log` in the
  module folder; the binary lands in `target/release`.
- Free-threaded builds are produced automatically on a free-threaded interpreter
  unless `XENOFORM_RS_DISABLE_FT` is set. Switching Python version or GIL mode
  invalidates compiled modules — a full rebuild (delete the `ext/` folder) is
  required.
- Return types are wrapped in `PyResult<>`; `&Bound<...>` references are stripped
  from return types. Keep `extension_types.py`, `rustmodule.py`, and the README's
  type-translation table consistent when changing the mapping.

## Workflow expectations

- Run lint, type check, and the test suite locally before pushing; CI runs the
  full matrix across three OSes and four Python versions.
- Keep changes focused and update `README.md` when user-visible behaviour changes.
- Do not commit generated extension artifacts (the `ext/` directory and Rust
  build output are ignored).
</content>
</invoke>
