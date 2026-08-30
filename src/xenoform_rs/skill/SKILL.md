---
name: xenoform-rs
description: >
  Use when writing, editing, or debugging @rust-decorated functions/methods in a Python
  project that uses xenoform-rs — inline Rust in a Python docstring, compiled via pyo3/cargo.
  Covers the @rust decorator, Python-to-Rust type translation, Annotated overrides, callable
  types, third-party crate dependencies, and the generated ext/ build artifacts. Triggers:
  "xenoform", "xenoform-rs", "xenoform_rs", "@rust", "rust_dependency", inline rust in a
  docstring, pyo3/cargo build errors under an `ext/` directory.
---

# Developing with xenoform-rs

xenoform-rs lets you write a type-annotated Python function, decorate it with `@rust`, and put
the Rust *body* of that function in its docstring. On import, xenoform-rs translates the Python
signature to Rust, generates a pyo3 extension crate under `ext/<module>_ext/`, compiles it with
`cargo`, and replaces the Python function with the compiled one. A hash of the source and
`Cargo.toml` is cached so unchanged modules are not rebuilt; the hash includes the interpreter
ABI (Python version, GIL vs free-threaded), so switching interpreters rebuilds automatically
into that interpreter's own cache subdirectory.

This skill is a quick reference. The canonical docs are the project's own `README.md` — read it
for the full walkthrough and worked examples (loop, distance matrix, Monte Carlo, Levenshtein).

## When `@rust` is worth reaching for

The reason to use it is **performance**, not taste — don't rewrite something in Rust just
because you can. Reach for `@rust` when profiling (or an obvious algorithmic shape) points at
one of these:

- **A sequential loop that can't be vectorised** — each iteration depends on the previous one
  (e.g. a running balance, a recurrence relation), so numpy has no vectorised form to fall back
  on and plain Python pays its per-iteration interpreter overhead on every step. The README's
  `loop.py` example shows an ~83x speedup at 10M rows purely from this.
- **A tight numeric loop where even vectorised numpy still loses** — vectorisation helps, but a
  compiled loop can still beat it, especially once you add real parallelism. `distance_matrix.py`
  shows rust+rayon beating a vectorised numpy baseline by ~57x at N=10,000.
- **Memory pressure from a vectorised approach, even when its wall-clock time is fine** — the
  Monte Carlo example's rust+rayon path is only ~2.4x faster than a multi-threaded numpy
  baseline at a million paths, but uses ~40x less peak memory, because it holds one path in
  registers at a time instead of materialising a whole `(n_paths, n_steps)` array. Worth
  reaching for `@rust` even for a modest speedup if the numpy version's memory footprint scales
  with input size in a way that will eventually hurt.
- **Non-numeric, allocation-heavy recurrences with no numpy angle at all** — e.g. string/DP
  algorithms like Levenshtein distance, where interpreting the recurrence in Python is what's
  slow, not the lack of vectorisation. `levenshtein_distances_rust` gets ~29x for exactly this
  reason.
- **Embarrassingly parallel work you want to spread across cores without the GIL getting in the
  way** — a one-line `rayon` change (`.into_par_iter()`) parallelises pure-Rust computation
  across all cores regardless of whether the Python interpreter is GIL-enabled or free-threaded.

Conversely, it's usually **not** worth it for: code that's already dominated by a vectorised
numpy/pandas call (the glue Python around it isn't the bottleneck), code that only runs rarely or
on small inputs (the one-time compile cost and added complexity outweigh the win), or code that
needs libraries/behaviour with no Rust equivalent readily available. When in doubt, write the
plain-Python version first and profile before reaching for `@rust`.

## Minimal example

```py
from xenoform_rs import rust

@rust(py=False)
def vector_sum(v: list[int]) -> int:  # a type checker will flag the empty body; that's expected
    """
    Ok(v.iter().sum())
    """
```

The docstring is the Rust function *body*: it must end in something producing the return type,
wrapped implicitly in `PyResult<...>` — return `Ok(value)`, or `Err(...)` to raise a Python
exception.

## `@rust` decorator parameters

| name | type | default | description |
|------|------|---------|--------------|
| `py` | `bool` | `True` | Pass the python context as the first argument (`py: Python<'py>`). Needed when creating Python objects or calling Python APIs from Rust. |
| `dependencies` | `list[str] \| None` | `None` | Rust crate dependencies. Use `rust_dependency(name, version=..., features=[...])` to build entries, e.g. `rust_dependency("numpy", version="0.28")`. |
| `modules` | `list[Path \| str] \| None` | `None` | Extra Rust source files to link in. Modifying one triggers a rebuild. |
| `imports` | `list[str] \| None` | `None` | Extra `use` imports, e.g. `"numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"`. |
| `module_name` | `str \| None` | `None` | Override the default python-file-to-rust-module name mapping — needed when the source file's name is a Rust keyword (e.g. a file called `loop.py` needs `module_name="loop_rs"`). |
| `profile` | `dict[str, str] \| None` | `None` | Overrides to the release Cargo profile, e.g. `{"strip": "symbols"}`. |
| `edition` | `str` | `"2024"` | The Rust edition. |
| `help` | `str \| None` | `None` | Docstring for the *Python* function (since the real docstring holds Rust code). |

## Default Python → Rust type mapping

| Python | Rust |
|--------|------|
| `None` | `()` |
| `int` | `i32` |
| `np.int32` / `np.int64` | `i32` / `i64` |
| `bool` | `bool` |
| `float` | `f64` |
| `np.float32` / `np.float64` | `f32` / `f64` |
| `complex` / `np.complex128` | `&Bound<'py, PyComplex>` |
| `str` | `String` |
| `np.ndarray` | `PyReadonlyArrayDyn` |
| `bytes` | `&'py [u8]` |
| `bytearray` | `&Bound<'py, PyByteArray>` |
| `list` | `Vec` |
| `set` / `frozenset` | `HashSet` |
| `dict` | `HashMap` |
| `tuple` | `(...)` |
| `slice` | `&Bound<'py, PySlice>` |
| `Any` / `Self` | `&Bound<'py, PyAny>` |
| `type` | `&Bound<'py, PyType>` |
| `*args` | `&Bound<'py, PyTuple>` |
| `**kwargs` | `Option<&Bound<'py, PyDict>>` |
| `T \| None` | `Option<T>` |
| `Callable` | `&Bound<'py, PyCFunction>` |
| `...` | `&Bound<'py, PyEllipsis>` |

Nested generics recurse: `dict[str, list[float]]` → `HashMap<String, Vec<f64>>`.

Override any of these with `Annotated`, e.g.:

```py
@rust(py=False)
def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]:  # ty: ignore[empty-body]
    """
    ...
    """
```

Return types are always wrapped in `PyResult<...>`, and any `&Bound<...>` in a *return* type has
its reference stripped (you get `Bound<'py, T>` back, since you can't return a borrow).

## Gotchas

- **Compound types beyond `T | None` aren't supported** — there's no mapping for e.g.
  `int | float` because it would need a Rust enum. Use an `Annotated` override to a generic
  type (`Annotated[int | float, "&Bound<'py, PyAny>"]`) or coerce to one Rust type
  (`Annotated[int | float, "f64"]`).
- **`complex` is 128-bit only** — no `np.complex64` support.
- **Callable *arguments* need the generic override.** The default `Callable` mapping
  (`&Bound<'py, PyCFunction>`) only accepts Rust-implemented callables, not Python
  functions/lambdas. To accept both, override to `&Bound<'py, PyAny>`:
  ```py
  @rust(py=False)
  def use_modulo(func: Annotated[Callable[[int], int], "&Bound<'py, PyAny>"], i: int) -> int:
      """
      func.call1((i,))?.extract::<i32>()
      """
  ```
  Callable *return* types work with the default mapping.
- **Only the mutable-array mapping (`npt.NDArray`) is actually mutable by default.** For `dict`,
  `list`, `set`, or `bytearray`, override to the corresponding pyo3 type (e.g. `PyList`) to
  mutate in place.
- **No linking to external prebuilt binaries.** Only source (the docstring plus any `modules=`
  files) is compiled.
- **Extra `modules=` files are copied into the crate** — editing them triggers a rebuild just
  like editing the docstring does.

## Configuration (environment variables)

| Variable | Effect |
|----------|--------|
| `XENOFORM_RS_PYO3_VERSION` | Override the pyo3 version (default and only supported: 0.28). |
| `XENOFORM_RS_EXTMODULE_ROOT` | Move compiled modules out of the default `ext/` subdirectory. Avoid path characters (space, hyphen) invalid in a Python module name. |
| `XENOFORM_RS_VERBOSE` | Any value (including empty) turns on INFO-level logging of compile/check/import steps with timings, on xenoform-rs's own logger only — never touches `logging.basicConfig`/root logging. |
| `XENOFORM_RS_DISABLE_FT` | Disable building free-threaded (GIL-free) extension modules under a free-threaded interpreter. |

## Troubleshooting a failed build

For a module `my_module.py`, generated artifacts live under `ext/my_module_ext/`:

- `src/lib.rs` — the generated Rust source; read this to see exactly what Rust code was produced
  from your Python signature.
- `build.log` — captured `cargo build` output.
- `target/<abi-tag>/release/` — the compiled shared library, one subdirectory per interpreter ABI.

Set `XENOFORM_RS_VERBOSE=1` to see each step (registering, hash check, import, redirect) with
timings on stderr.

## Working on xenoform-rs itself (not just using it)

If you're editing this library's own source (`src/xenoform_rs/`) rather than using it in a
downstream project, this repo's `AGENTS.md` governs the workflow: plan and get sign-off before
non-trivial changes, run the full quality-gate suite (`ruff check`, `ruff format --check`,
`ty check`, `pytest`, and `examples/*.py`) before calling anything done, and add a
Why/What/Design-decisions/Follow-ups entry to `JOURNAL.md` for every task.
