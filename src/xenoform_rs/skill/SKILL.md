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
the Rust *body* of that function in its docstring. Importing the module only registers each
decorated function. On the first call to any of them, xenoform-rs translates the Python
signatures to Rust, generates one pyo3 extension crate for the module under `ext/<module>_ext/`,
compiles it with `cargo`, and replaces the Python functions with the compiled ones — so build
errors surface at that first call, not at import. A hash of the source and `Cargo.toml` is stored
in the module folder so unchanged modules are not rebuilt; each interpreter
ABI (Python version, GIL vs free-threaded) has its own binaries and hashes, so switching
interpreters rebuilds automatically into that interpreter's own cache subdirectory.

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
on small inputs (the one-time compile cost and added complexity outweigh the win), code that
needs libraries/behaviour with no Rust equivalent readily available, or code that has to ship as
prebuilt binaries (a wheel, or an image without a Rust toolchain): xenoform-rs compiles on the
machine that runs it, so use [maturin](https://www.maturin.rs/) for that. When in doubt, write the
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

Default argument values, positional-only/keyword-only markers (`/`, `*`), `*args` and `**kwargs`
are all supported.

### Methods

Instance, static and class methods work. `self` is a Rust keyword, so name the instance parameter
something else (by convention `pyself`, typed `Self`). Put `@staticmethod`/`@classmethod`
*above* `@rust`:

```py
class Thing:
    @rust(py=False)
    def method(pyself: Self) -> int:  # noqa: N805
        """
        pyself.getattr("x")?.extract::<i32>()
        """

    @staticmethod
    @rust(py=False)
    def static_method(i: int) -> int:
        """
        Ok(i + 1000)
        """
```

## `@rust` decorator parameters

| name | type | default | description |
|------|------|---------|--------------|
| `py` | `bool` | `True` | Pass the python context as the first argument (`py: Python<'py>`). Needed when creating Python objects or calling Python APIs from Rust. |
| `dependencies` | `list[str] \| None` | `None` | Rust crate dependencies. Use `rust_dependency(name, version=..., features=[...])` to build entries. For numpy use `NUMPY_CRATE`, which matches pyo3's version: a separately pinned numpy that pulls in a different pyo3 won't build. |
| `modules` | `list[Path \| str] \| None` | `None` | Extra Rust source files to link in. Modifying one triggers a rebuild. |
| `imports` | `list[str] \| None` | `None` | Extra `use` imports, e.g. `"numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"`. |
| `module_name` | `str \| None` | `None` | Override the default python-file-to-rust-module name mapping — needed when the source file's name is a Rust keyword (e.g. a file called `loop.py` needs `module_name="loop_rs"`). |
| `profile` | `dict[str, str] \| None` | `None` | Overrides to the release Cargo profile, e.g. `{"strip": "symbols"}`. |
| `edition` | `str` | `"2024"` | The Rust edition. |
| `help` | `str \| None` | `None` | Docstring for the *Python* function (since the real docstring holds Rust code). |
| `link_search` | `list[Path \| str] \| None` | `None` | Directories to search for external libraries (relative to the working directory). |
| `link_libs` | `list[str] \| None` | `None` | External libraries to link, as rustc `-l` values, e.g. `"static=foo"`, `"dylib=foo"`. |
| `link_args` | `list[str] \| None` | `None` | Raw linker arguments, e.g. `"-Wl,-rpath,/opt/foo/lib"` so a shared library is found at import. |
| `constants` | `list[str] \| None` | `None` | Names of Python variables (local, class-body, module-level or imported) emitted as module-level `const` items with the same name, typed from the value (`int` → `i32`, `str` → `&str`). For another type write `"NAME: u64"`. An `Annotated` annotation on the Python variable is **ignored**, because it doesn't travel with an imported value. |

## Default Python → Rust type mapping

| Python | Rust |
|--------|------|
| `None` | `()` |
| `int` | `i32` |
| `np.int8` / `np.int16` / `np.int32` / `np.int64` | `i8` / `i16` / `i32` / `i64` |
| `np.uint8` / `np.uint16` / `np.uint32` / `np.uint64` | `u8` / `u16` / `u32` / `u64` |
| `bool` | `bool` |
| `float` | `f64` |
| `np.float32` / `np.float64` | `f32` / `f64` |
| `complex` / `np.complex128` | `&Bound<'py, PyComplex>` |
| `str` | `String` |
| `np.ndarray` / `npt.NDArray` | `PyReadonlyArrayDyn` |
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
| `datetime` | `jiff::Zoned` |
| `timedelta` | `jiff::SignedDuration` |
| `date` | `jiff::civil::Date` |
| `time` | `jiff::civil::Time` |
| `tzinfo` | `jiff::tz::TimeZone` |

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

- **`RustTypeError: Don't know a Rust type for ...`** means the type has no default mapping. Add an
  `Annotated` override with the Rust type you want; the override replaces the whole type, so
  unmapped type parameters inside it (e.g. `npt.NDArray[np.datetime64]`) are fine.
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
  mutate in place. For a safe writable numpy array, take `&Bound<'py, PyArray1<f64>>` and call
  `.try_readwrite()?`: it raises on a read-only array (e.g. from pandas copy-on-write), whereas a
  `PyReadwriteArray1` argument panics.
- **Rust code must be threadsafe under a free-threaded interpreter.** There, extension modules
  are built without the GIL by default; set `XENOFORM_RS_DISABLE_FT` to opt out.
- **`datetime` must be timezone-aware by default.** It maps to `jiff::Zoned`, which accepts
  `timezone.utc`, fixed offsets and `zoneinfo.ZoneInfo` (and `pd.Timestamp`, a `datetime`
  subclass), keeping IANA names and DST rules. A naive datetime raises `TypeError`. For naive
  datetimes, use a type override to the civil type — it rejects aware ones, and its arithmetic
  is wall-clock, with no DST:
  ```py
  @rust(py=False, dependencies=[rust_dependency("jiff", version="0.2")])
  def add(t: Annotated[datetime, "jiff::civil::DateTime"], dt: timedelta) -> Annotated[datetime, "jiff::civil::DateTime"]:
      """
      Ok(t + dt)
      """
  ```
  Either way, add the `jiff` crate with `rust_dependency("jiff", version="0.2")`. Nanoseconds in
  a `pd.Timestamp` are dropped. Known pyo3 bug (0.29.3, still in 0.30): a `Zoned` *returned* in
  the repeated hour after clocks go back comes back an hour early (`fold` is lost).
- **`date`, `time` and `tzinfo` drop information silently.** A `datetime` passed as a `date`
  loses its time (`datetime` subclasses `date`), and a `time`'s `tzinfo` and `fold` are
  dropped. `tzinfo` (→ `jiff::tz::TimeZone`) accepts `ZoneInfo`, `timezone.utc` and fixed
  offsets, and comes back as the same kind.
- **Never pass `pd.NaT`: it isn't `None`, so `datetime | None` doesn't catch it** — `NaT` is a
  `datetime` subclass with no data. It raises `TypeError` for `datetime` and `timedelta`. As a
  `date` or civil type it **is silently read as 0001-01-01** (its underlying date fields). For a
  list, replace it with `None` and take `list[datetime | None]`:
  `list(idx.astype(object).where(idx.notna(), None))`. For speed, pass
  `idx.tz_convert(None).as_unit("us").to_numpy()` (drop `tz_convert(None)` if naive) as
  `Annotated[npt.NDArray[np.datetime64], "PyReadonlyArray1<'py, Datetime<Microseconds>>"]`
  (imports `numpy::datetime::{Datetime, units::Microseconds}`), where `NaT` is `i64::MIN`.
- **External libraries are linked, not tracked.** Use `link_search`/`link_libs` (and
  `link_args` for an rpath); declare the functions in an `unsafe extern "C" { ... }` block and call them
  in `unsafe`. Rebuilding the library doesn't rebuild the module: delete its `ext/` folder. Static
  libraries need `-fPIC`; a shared library needs an rpath (or `LD_LIBRARY_PATH`, or
  `os.add_dll_directory` on windows) to be found at import.
- **Extra `modules=` files are copied into the crate** — editing them triggers a rebuild just
  like editing the docstring does.

## Configuration (environment variables)

| Variable | Effect |
|----------|--------|
| `XENOFORM_RS_PYO3_VERSION` | Override the pyo3 version (default and only supported: 0.30). `NUMPY_CRATE` follows it at the minor version. |
| `XENOFORM_RS_EXTMODULE_ROOT` | Move compiled modules out of the default `ext/` subdirectory. Avoid path characters (space, hyphen) invalid in a Python module name. |
| `XENOFORM_RS_VERBOSE` | Any value (including empty) turns on INFO-level logging of compile/check/import steps with timings, on xenoform-rs's own logger only — never touches `logging.basicConfig`/root logging. |
| `XENOFORM_RS_DISABLE_FT` | Disable building free-threaded (GIL-free) extension modules under a free-threaded interpreter. |
| `XENOFORM_RS_BUILD_TIMEOUT` | Build timeout in seconds (positive, default 300). Raise it for heavy dependency trees. A timeout raises `CompilationError`. |

## Notebooks

- **Functions defined in a cell need `module_name=`**, e.g. `@rust(py=False, module_name="nb")`:
  the default module name comes from the source file, and Jupyter's cell files aren't valid
  module names.
- **Running the defining cell only registers the function.** The module compiles when a cell
  first calls one of its functions, and compile errors appear in *that* cell's output.
- **Changes need a kernel restart**, whether the `@rust` function is in a cell or an imported
  `.py` file (`%autoreload` doesn't help): a process can't unload a compiled module.

## Troubleshooting a failed build

A failed build raises `CompilationError` at the first call. Its message holds rustc's errors,
shortened: only those with a suggested fix (or else the first), without notes about code outside
the module. All errors are on `e.diagnostics` as `RustDiagnostic` objects (`code`, `message`,
`file`, `line`); line numbers refer to the generated `src/lib.rs`. Errors from before rustc runs
(e.g. an invalid `profile` or `edition`) are in the message, with `diagnostics` empty.

A successful build with rustc warnings issues each as a `RustWarning` (a `UserWarning`), only when
the module is (re)built. Turn them into errors with `warnings.simplefilter("error", RustWarning)`
or pytest's `filterwarnings = ["error::xenoform_rs.RustWarning"]`.

For a module `my_module.py`, generated artifacts live under `ext/my_module_ext/`:

- `src/lib.rs` — the generated Rust source; read this to see exactly what Rust code was produced
  from your Python signature.
- `build.log` — captured `cargo build` output.
- `<abi-tag>.checksum` — the hash of the sources that interpreter's binary was built from. Deleting
  it (or the whole folder) forces a rebuild.

The compiled shared library is in `ext/target/<abi-tag>/release/`, a cargo target directory shared by
every module (one subdirectory per interpreter ABI). A `target/` folder inside `ext/my_module_ext/` is
left over from xenoform-rs 0.1.6 or earlier and can be deleted.

Set `XENOFORM_RS_VERBOSE=1` to see each step (registering, hash check, import, redirect) with
timings on stderr.

## Working on xenoform-rs itself (not just using it)

If you're editing this library's own source (`src/xenoform_rs/`) rather than using it in a
downstream project, this repo's `AGENTS.md` governs the workflow: plan and get sign-off before
non-trivial changes, run the full quality-gate suite (`ruff check`, `ruff format --check`,
`ty check`, `pytest`, and `examples/*.py`) before calling anything done, and add a
Why/What/Design-decisions/Follow-ups entry to `JOURNAL.md` for every task.
