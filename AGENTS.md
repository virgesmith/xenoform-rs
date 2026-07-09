# Agent Guidelines for `xenoform-rs`

This file instructs AI agents acting as developer, reviewer, and QA for this repository.

## Collaboration & Ownership

The maintainer must retain **ownership** of this codebase — meaning they understand
every change well enough to explain, defend, and modify it without the agent. The
agent's speed serves that understanding; it does not replace it. Follow these rules
of engagement:

1. **Plan before code, and wait for approval.** For any non-trivial change, present
   a plan first — approach, files touched, trade-offs — and do not write code until
   the maintainer has understood and signed off. If a decision in the plan can't be
   evaluated yet, stop and explain it.
2. **Small, reviewable diffs — never a big-bang drop.** Break large work into
   increments that can be read in one sitting and reviewed one at a time.
3. **Leave the load-bearing parts to the maintainer when asked.** Offer to hand off
   the core algorithm or tricky module rather than always doing everything; default
   to boilerplate, tests, plumbing, and review.
4. **Explain-it-back gate.** Before proposing a merge, make sure the maintainer can
   explain *why* the change works and what the alternatives were. Offer a
   walk-through; act as tutor, not just producer.
5. **Justify trade-offs, not just conclusions.** State *why* this data structure,
   error type, or approach — and why not the obvious alternative. The reasoning is
   the transferable knowledge.
6. **Prefer idioms the maintainer can learn from**, especially in Rust. Flag new or
   unusual patterns and point to where to read more, rather than using them silently.
7. **Tests are the readable spec.** Keep them clear enough that reading the tests
   conveys the contract even when the implementation is dense.

## Task & Design Summaries

**Every task/PR must be recorded** as a new entry at the top of [JOURNAL.md](JOURNAL.md).
Each entry records:

- **Why** — the motivation for the change and the problem it solves.
- **What** — a short description of the change at a high level.
- **Design decisions** — the choices made, the alternatives considered, and why each
  was accepted or rejected. Capture any non-obvious trade-offs or constraints here
  rather than only in code comments.
- **Follow-ups** — anything deferred, and known limitations.

Write the entry as part of the change, not after the fact — the journal is the durable
record of intent that keeps the maintainer in control of the codebase's direction.

## Project Overview

`xenoform-rs` is a Python library that lets you write and execute Rust code inline in Python. You annotate a Python function with the `@rust` decorator and put the Rust implementation in its docstring; on import, the library translates the Python type signatures to Rust types, generates a pyo3 extension module, compiles it with `cargo`, and replaces the Python function with the compiled Rust one.

The library source lives in [src/xenoform_rs/](src/xenoform_rs/). Key modules:

| File | Role |
|------|------|
| [compile.py](src/xenoform_rs/compile.py) | Rust source generation and `cargo` invocation |
| [rustmodule.py](src/xenoform_rs/rustmodule.py) | Module-level import hook and hash-based change detection |
| [extension_types.py](src/xenoform_rs/extension_types.py) | Python → Rust type translation |
| [config.py](src/xenoform_rs/config.py) | `pydantic-settings`-backed configuration |
| [errors.py](src/xenoform_rs/errors.py) | Library-specific exception types |
| [utils.py](src/xenoform_rs/utils.py) | Shared utilities |
| [__init__.py](src/xenoform_rs/__init__.py) | Public exports (`rust`, `rust_dependency`) |

Tests are in [src/test/](src/test/). Examples are in [examples/](examples/).

## Toolchain

| Tool | Command |
|------|---------|
| Package manager | `uv` |
| Linter / formatter | `ruff` (`uv run ruff check`, `uv run ruff format`) |
| Type checker | `ty` (`uv run ty check src`) |
| Tests | `uv run pytest -sv` |
| Install dev deps | `uv sync --dev --all-extras` |

**Rust is required.** Tests compile real Rust code at runtime — ensure `rustup` and a stable toolchain are installed (`rustup toolchain install stable`).

Pre-commit hooks run `uv-lock`, `ruff-check --fix`, `ruff-format`, and `ty` automatically on commit.

## Quality Gates

All of the following must pass before any change is considered complete:

```sh
uv run ruff check          # zero lint errors
uv run ruff format --check # zero formatting issues
uv run ty check src        # zero type errors
uv run pytest -sv          # all tests pass
uv run examples/loop.py           # examples still work
uv run examples/distance_matrix.py
```

There is no coverage threshold configured, but tests compile and execute real Rust, so they are inherently integration-level — every code path should be exercised.

## Developer Rules

- **Runtime dependencies are intentional.** `itrx`, `numpy`, and `pydantic-settings` are runtime deps. New runtime deps need a strong justification; dev-only tools go in `[dependency-groups.dev]` in [pyproject.toml](pyproject.toml).
- **Type translation is the critical path.** Changes to [extension_types.py](src/xenoform_rs/extension_types.py) affect every user and must be accompanied by tests covering the affected type mappings.
- **Generated Rust must compile.** When modifying the code generation in [compile.py](src/xenoform_rs/compile.py), verify the output is valid Rust — run the full test suite, which will catch this.
- **The `Annotated` override mechanism is the escape hatch.** Do not special-case types in the core translation logic when an `Annotated` override can solve the problem instead.
- **Free-threaded support must be preserved.** The library builds GIL-free extension modules when running under free-threaded Python (`3.14t`). Changes affecting the pyo3 bindings or module build flags must not regress free-threaded behaviour.
- **Type annotations required.** All function signatures need full annotations. `ty` will catch missing or incorrect ones.
- **Line length is 120** (configured in [pyproject.toml](pyproject.toml) under `[tool.ruff]`).
- **No comments explaining what the code does.** Only add a comment when the *why* is non-obvious (hidden constraint, workaround, subtle invariant).

## Reviewer Checklist

When reviewing a PR or diff, check:

1. **Correctness** — does the type translation produce valid Rust? Edge cases: nested generics, `Optional`, `Annotated` overrides, `*args`/`**kwargs`, callable types.
2. **Rust output validity** — mentally trace the generated `src/lib.rs` for any new type mapping; the test suite will catch compilation failures but reasoning first saves time.
3. **Change detection** — does the hash check in [rustmodule.py](src/xenoform_rs/rustmodule.py) still correctly trigger rebuilds after the change?
4. **Free-threaded correctness** — anything touching the module build or pyo3 bindings must work under `3.14t`.
5. **Test coverage** — each new type, decorator parameter, or error path needs a test in [src/test/](src/test/).
6. **API consistency** — new `@rust` decorator parameters must follow the existing naming conventions and be documented in [README.md](README.md).
7. **Types** — return types and generics should be precise. Avoid `Any` unless unavoidable.
8. **Ruff rules** — no rule in the `select` list should be suppressed without justification. Active rules: `ARG, B, C, D103, E, F, I, N, PERF, PTH, RET, RUF, SIM, UP, W` (E501 ignored; D103 also ignored in test files).
9. **README / examples** — if the public API or type table changes, update [README.md](README.md) and verify the examples still run.

## QA Rules

- Run the full gate suite (`ruff check`, `ruff format --check`, `ty check`, `pytest`, both examples) before declaring any task done.
- CI runs the matrix: Python 3.12, 3.13, 3.14, 3.14t × ubuntu, macos, windows. Flag anything that might be platform- or version-specific, especially path handling (`PTH` rules) and free-threaded behaviour.
- The free-threaded build (`3.14t`) is in the CI matrix. Do not assume it behaves identically to the standard build.
- If a test is skipped or marked `xfail`, leave a comment explaining why and when it can be removed.

## Repository Layout

```
src/
  xenoform_rs/
    __init__.py         # public exports: rust, rust_dependency
    compile.py          # Rust source generation and cargo invocation
    rustmodule.py       # import hook, hash-based change detection
    extension_types.py  # Python → Rust type translation
    config.py           # pydantic-settings configuration
    errors.py           # exception types
    utils.py            # shared utilities
    py.typed            # PEP 561 marker
  test/
    test_basic.py
    test_basic_again.py
    test_callable.py
    test_complex.py
    test_compound_types.py
    test_compound_type_error.py
    test_config.py
    test_container_types.py
    test_edition_conflict.py
    test_edition_invalid.py
    test_freethreaded.py
    test_help.py
    test_inplace.py
    test_kwargs.py
    test_method.py
    test_modules.py
    test_modules_error.py
    test_module_name_override.py
    test_module_name_override2.py
    test_nested.py
    test_numpy.py
    test_profile_conflict.py
    test_profile_invalid.py
    test_slice.py
    test_types.py
    test_typing.py
    test_utils.py
    fibonacci.rs        # auxiliary Rust source used by test_modules.py
    other_module.py     # auxiliary Python module used by tests
examples/
  loop.py
  distance_matrix.py
.github/workflows/
  lint-test.yml         # CI: lint + type check + test matrix + examples
  publish.yml           # CI: PyPI publish on tag
README.md
pyproject.toml
.pre-commit-config.yaml
```

## Branch and Release Policy

- **`main` is branch-protected.** Direct pushes are blocked. All changes must go through a pull request.
- **Releases are triggered by a `v*` tag** (e.g. `v0.1.3`). Pushing such a tag runs [publish.yml](.github/workflows/publish.yml), which builds a wheel and publishes to PyPI via trusted publishing (OIDC — no API token needed). Do not push a `v*` tag unless the release is fully ready and the version in [pyproject.toml](pyproject.toml) matches the tag.
- Version bumps go in `pyproject.toml` (`version = "x.y.z"`).

## Workflow

1. Agree the plan with the maintainer before writing code (see [Collaboration & Ownership](#collaboration--ownership)).
2. Create a feature branch off `main` — never commit directly to `main`.
3. Make changes under [src/xenoform_rs/](src/xenoform_rs/).
4. Add or update tests in [src/test/](src/test/) — each new type mapping, parameter, or error path needs coverage.
5. Add a task/design entry to [JOURNAL.md](JOURNAL.md) (see [Task & Design Summaries](#task--design-summaries)).
6. Run the full gate suite locally (including the examples).
7. If the public API or type translation table changed, update [README.md](README.md).
8. Commit — pre-commit hooks will auto-fix formatting and re-lock `uv.lock`.
9. Open a PR targeting `main`; CI must pass (all OS × Python version combinations) before merging.
10. To release: bump the version in [pyproject.toml](pyproject.toml), merge to `main`, then push a `vX.Y.Z` tag — PyPI publish triggers automatically.
