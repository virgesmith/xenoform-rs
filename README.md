# xenoform-rs

Write and execute superfast *rust* inside your Python code! Here's how...

Write a type-annotated function or method definition **in python**, add the `rust` decorator and put the **rust
implementation** in a docstr:

```py
from xenoform_rs import rust

@rust(py=False)
def vector_sum(v: list[int]) -> int:  # ty: ignore[empty-body]
    """
    Ok(v.iter().sum())
    """
```

Here's what happens automatically when you import a module with `@rust`-decorated functions:

**First call or after code changes:**

1. Rust source code is generated - your Python type signatures are translated to Rust types
2. The extension module is compiled
3. Your decorated Python functions are replaced with their compiled Rust implementations

**Subsequent calls:**
The Rust functions execute directly with minimal overhead.

**Change detection:**
Each module stores a hash of its source code and Cargo.toml. On import, xenoform-rs checks these hashes and
automatically rebuilds the module if any changes are detected. The interpreter ABI (Python version, and whether the
build is GIL-enabled or free-threaded) is part of this hash, so switching Python versions or GIL/free-threaded builds
triggers a rebuild automatically. Each interpreter builds into its own subdirectory, so switching back and forth reuses
each cached build rather than recompiling.

**Where files go:**
By default, the `ext` subfolder contains binaries, generated source code, and build logs. To change this location see
[below](#location-of-extension-modules).

## Features

- Supports `numpy` arrays (via the `numpy` crate) for customised "vectorised" operations.
- Using annotated types, you can override the default mapping of python types to rust types.
- Supports positional and keyword arguments with defaults, including positional-only and keyword-only markers (`/`,`*`)
- Supports `*args` and `**kwargs`, mapped  (respectively) to `&Bound<'py, PyTuple>` and `Option<&Bound<'py, PyDict>>`.
NB type annotations for these types are still useful for python type checkers. See [test_kwargs.py](src/test/test_kwargs.py)
- Supports custom dependencies and imports.
- Callable types are supported both as arguments and return values. See [below](#callable-types).
- Optional (`T | None`) types are supported, mapping to `Option<T>`
- Can link to separate rust sources, see [test_modules.py](src/test/test_modules.py) for details.
- By [default](#free-threaded-interpreter), supports parallel execution when the python interpreter is free-threaded.

Caveats & points to note:

- callable types (more detail [below](#callable-types)):
    - only generic (untyped) functions/closures are supported.
    - a type override is necessary to pass functions as arguments. The default works for return values.
- complex: 128 bit support only (i.e. not `np.complex64`)
- if additional modules are specified, the files are copied into the crate. Modifications to additional modules will
trigger a rebuild.
- no support for compound types, other than optional (`T | None`) (This would require building support for rust enums).
Use a type override to a generic python type e.g. `Annotated[int | float, "&Bound<'py, PyAny>"]` or coerce to a single
rust type e.g. `Annotated[int | float, "f64"]`.
- no support currently for linking to external prebuilt binaries
- due to restrictions arising from linguistic differences, xenoform-rs will likely never be as functionally complete
than its C++ sister, [xenoform](https://pypi.org/project/xenoform/)

## Getting started

Install the package

```sh
uv add xenoform-rs  # or pip install xenoform-rs
```

> **Using an AI coding agent?** xenoform-rs ships an installable [agent skill](#agent-skill) —
> run `uv run xenoform-rs-skill --install` and your agent gets a built-in reference for writing
> `@rust`-decorated code correctly, without needing this whole README in context.

Simply decorate your rust-implemented functions with the `rust` decorator factory - it handles all the configuration and compilation. Here's a function that counts the elements in a multidimensional array:

```py
from typing import Annotated

import numpy as np
import numpy.typing as npt

from xenoform_rs import rust, rust_dependency


@rust(
    py=False,  # we don't require the python context as the first argument (we aren't constructing any python objects or calling any python APIs)
    dependencies=[rust_dependency("numpy", version="0.28")],  # declare we need the numpy crate
    imports=["numpy::PyReadonlyArrayDyn"],  # import the type we need
)
def array_nelems(a: npt.NDArray[np.int64]) -> Annotated[int, "usize"]:
    # npt.NDArray[np.int64] maps by default to numpy::PyReadOnlyArrayDyn<i64>
    # the return type is a rust usize which gets converted to a python int
    """
    Ok(a.as_array().shape().iter().product())
    """

if __name__ == "__main__":
    print(array_nelems(np.empty([2, 3, 5, 7], dtype=np.int64)))
```

## Agent skill

xenoform-rs ships a `SKILL.md` for AI coding agents (e.g. Claude Code) covering the `@rust`
decorator, the type-translation tables below, and common gotchas, so an agent doesn't need this
whole README in context to write correct `@rust`-decorated code.

Install it into a project as a symlink to the version installed in the current environment:

```sh
uv run xenoform-rs-skill --install [PATH]  # default PATH: .agents
uv run xenoform-rs-skill --remove [PATH]   # default PATH: .agents
```

(Or, without `uv`, activate the virtualenv `xenoform-rs` is installed in and drop the `uv run`
prefix — `xenoform-rs-skill` is a normal console-script entry point, so it's only on `PATH` while
that environment is active.)

This creates (or removes) `PATH/skills/xenoform-rs`, symlinked to the skill bundled inside the
installed `xenoform-rs` package, so it always matches the version in use.

## The `@rust` decorator factory parameters

name | type | default | description
---- | ---- | ------- | -----------
`py` | `bool` | `True` | Pass the python context as the first argument. Necessary when (e.g.) creating python objects
`dependencies` | `list[str] \| None` | `None` | Rust package dependencies, the `rust_dependency` convenience function can be used to specify dependency parameters, e.g. `dependencies=[rust_dependency("numpy", version="0.28")]`
`modules` | `list[Path \| str] \| None` | `None` | Sources for additional modules
`imports` | `list[str] \| None` | `None` | Additional imports, e.g. `imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"]`
`module_name` | `str \| None` | `None` | Override the default one-to-one mapping between python files and rust modules, e.g. when the python source file is a reserved rust keyword
`profile` | `dict[str, str] \| None` | `None` | Overrides to (release mode) [profile](https://doc.rust-lang.org/cargo/reference/profiles.html), e.g. optimisation level, strip symbols, etc.
`edition` | `str` | `"2024"` | The rust edition
`help` | `str \| None` | `None` | Docstring for the function

## Performance

Rust can offer very significant performance enhancements over python, especially where *vectorised* &ast; operations are not available, but even when they are.

> &ast; "vectorisation" in this sense means implementing loops in compiled - rather than interpreted - code. In fact, the compiler also has various optimisations available to it including but by no means limited to "true" vectorisation (meaning hardware SIMD instructions).

The first example deals with an operation on a pandas Series that must be done sequentially, and the second shows that significant performance gains can be had even when a vectorised python implementation is available. Running these examples requires the "examples" optional dependencies (and of course [rust](https://rust-lang.org/tools/install/)):

```sh
uv add xenoform-rs --extra examples  # or pip install xenoform-rs[examples]
```

### Loop

This is a Rust vs python comparison of a non-vectorisable sequential operation on a `pd.Series`. First a python
implementation...

```py
def calc_balances_py(data: pd.Series, rate: float) -> pd.Series:
    """Cannot vectorise, since each value is dependent on the previous value"""
    result = pd.Series(index=data.index)
    # Directly access the underlying numpy array for performance. pandas>=3 returns a read only array, so make it writeable
    result_np = result.to_numpy()
    result_np.flags.writeable = True
    current_value = 0.0
    for i, value in data.items():
        current_value = (current_value + value) * (1 - rate)
        result_np[i] = current_value
    return result
```

...and the equivalent rust implementation. Note that pyo3/rust knows nothing about pandas, but can still work with
such objects via their python API:

```py
@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArray1, PyArrayMethods}", "pyo3::types::{PyDict, PyAnyMethods}"],
    module_name="loop_rs",  # override as "loop" is a rust keyword
    profile={"strip": "symbols"},
)
def calc_balances_rust(
    data: Annotated[pd.Series, "&Bound<'py, PyAny>"], rate: float
) -> Annotated[pd.Series, "Bound<'py, PyAny>"]:  # ty: ignore[empty-body]
    """
```

```rs
    // extract numpy arrays from the series. Note input is i64, output is f64
    let data_obj = data.call_method0("to_numpy")?;
    let data_np: &Bound<'py, PyArray1<i64>> = data_obj.cast()?;
    let n = data_np.len()?;

    // use the pattern from the numpy documentation
    let result_np = unsafe {
        let r = PyArray1::<f64>::zeros(py, [n], false);
        let mut current_value = 0.0;

        for i in 0..n {
            current_value = (current_value + *data_np.uget([i]) as f64) * (1.0 - rate);
            *r.uget_mut([i]) = current_value;
        }
        r
    };

    // Construct a pd.Series with the same index as the input
    let pd = py.import("pandas")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("index", data.getattr("index")?)?;
    pd.getattr("Series")?.call((result_np,), Some(&kwargs))
```

```py
    """
```

Performance comparison:

N | py (ms) | rust (ms) | speedup
-:|--------:|----------:|-----------:
1000 | 0.5 | 1.2 | -60%
10000 | 2.0 | 0.1 | 2235%
100000 | 18.7 | 0.5 | 3654%
1000000 | 192.8 | 2.7 | 7131%
10000000 | 1894.8 | 22.8 | 8214%

Full code is in [examples/loop.py](examples/loop.py).

### Distance Matrix

In this example we compute a distance matrix between $N$ points in $D$ dimensions. An efficient `numpy` implementation
could be:

```py
def calc_dist_matrix_py(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))
```

bearing in mind there is some redundancy here as the resulting matrix is symmetric; however vectorisation with
redundancy will always win the tradeoff against loops with no redundancy. But a rust implementation is significantly
faster, and here we go a step further and parallelise it with [`rayon`](https://crates.io/crates/rayon). The matrix is
filled one row per parallel task: `par_chunks_mut(n)` hands each task a disjoint mutable row, so the writes are
race-free without any `unsafe` and without threads mirroring each other's cells. This computes the full matrix rather
than exploiting symmetry, but the embarrassingly parallel scaling more than pays for the extra arithmetic:

```py
@rust(
    dependencies=[
        rust_dependency("numpy", version="0.28"),
        rust_dependency("rayon", version="1.11"),
    ],
    imports=[
        "numpy::{PyArray1, PyArray2, PyArrayMethods, PyReadonlyArray2}",
        "rayon::prelude::*",
    ],
)
def calc_dist_matrix_rust(
    points: Annotated[npt.NDArray[np.float64], "PyReadonlyArray2<f64>"],
) -> Annotated[npt.NDArray[np.float64], "Bound<'py, PyArray2<f64>>"]:
    """
```

```rs
    let points = points.as_array();
    let shape = points.shape();
    let (n, d) = (shape[0], shape[1]);

    // fill a plain Vec in parallel: each row is a disjoint chunk, so there are no races
    // and no need to mirror the upper triangle across threads.
    let mut data = vec![0.0f64; n * n];
    data.par_chunks_mut(n).enumerate().for_each(|(i, row)| {
        for j in 0..n {
            let mut sum = 0.0;
            for k in 0..d {
                let diff = points[[i, k]] - points[[j, k]];
                sum += diff * diff;
            }
            row[j] = sum.sqrt();
        }
    });

    let result = PyArray1::from_vec(py, data).reshape([n, n])?;
    Ok(result)
```

```py
    """
```

N | py (ms) | rust (ms) | speedup
-:|--------:|----------:|-----------:
100 | 0.7 | 0.4 | 98%
300 | 7.4 | 0.4 | 1580%
1000 | 41.9 | 1.1 | 3600%
3000 | 319.1 | 6.8 | 4608%
10000 | 3954.3 | 69.8 | 5567%

Full code is in [examples/distance_matrix.py](examples/distance_matrix.py).

### Monte Carlo simulation

This example compares optimised parallel Monte Carlo simulations pricing an arithmetic-average Asian call option - a tight RNG loop over `n_paths × n_steps` iterations - comparing multi-core python/numpy against multi-core rust. It also shows how to use third-party crates (`rand`, `rand_distr`, `rayon`) and how `rayon` parallelises pure-rust computation across all cores - independently of the python interpreter, so it works even on GIL-enabled builds.

The python baseline is numpy at its best: vectorised, in-place, and sharded across a thread pool. Even so it has
two handicaps rust doesn't. Vectorisation means materialising the whole `(n_paths, n_steps)` matrix - 2GB at a
million paths - so the threads compete for memory bandwidth, and scaling plateaus well short of the core count.
And because numpy ufuncs are single-threaded, the multi-core version needs manual sharding with independent
deterministic RNG streams per shard via `SeedSequence.spawn`:

```py
def _payoff_sum_np(
    s0: float, k: float, r: float, sigma: float, t: float, n_steps: int, n_paths: int, rng: np.random.Generator
) -> float:
    "Sum of Asian call payoffs over n_paths simulated paths (in-place, to peak at one (n_paths, n_steps) matrix)"
    dt = t / n_steps
    drift = (r - 0.5 * sigma * sigma) * dt
    vol = sigma * math.sqrt(dt)
    z = rng.standard_normal((n_paths, n_steps))
    z *= vol
    z += drift
    np.cumsum(z, axis=1, out=z)
    np.exp(z, out=z)
    return float(np.maximum(s0 * z.mean(axis=1) - k, 0.0).sum())


def price_asian_option_np_threads(
    s0: float, k: float, r: float, sigma: float, t: float, n_steps: int, n_paths: int, seed: int
) -> float:
    "Shard the paths across a thread pool, each with an independent RNG stream"
    counts = [n_paths // N_THREADS + (i < n_paths % N_THREADS) for i in range(N_THREADS)]
    rngs = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(N_THREADS)]
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        sums = ex.map(lambda n, rng: _payoff_sum_np(s0, k, r, sigma, t, n_steps, n, rng), counts, rngs)
    return math.exp(-r * t) * sum(sums) / n_paths
```

The rust implementation, by contrast, holds each path in a register, allocates nothing, and parallelises with a
one-line `rayon` change (`into_par_iter`):

```py
@rust(
    py=False,
    dependencies=[
        rust_dependency("rand", version="0.9", features=["small_rng"]),
        rust_dependency("rand_distr", version="0.5"),
        rust_dependency("rayon", version="1.11"),
    ],
    imports=[
        "rand::{Rng, SeedableRng}",
        "rand::rngs::SmallRng",
        "rand_distr::StandardNormal",
        "rayon::prelude::*",
    ],
    profile={"strip": "symbols"},
)
def price_asian_option_rayon(
    s0: float,
    k: float,
    r: float,
    sigma: float,
    t: float,
    n_steps: Annotated[int, "usize"],
    n_paths: Annotated[int, "usize"],
    seed: Annotated[int, "u64"],
) -> float:
    """
```

```rs
    let dt = t / n_steps as f64;
    let drift = (r - 0.5 * sigma * sigma) * dt;
    let vol = sigma * dt.sqrt();
    // one independently-seeded RNG per path keeps the result deterministic regardless of scheduling
    let payoff_sum: f64 = (0..n_paths)
        .into_par_iter()
        .map(|i| {
            let mut rng = SmallRng::seed_from_u64(seed.wrapping_add(i as u64));
            let mut s = s0;
            let mut total = 0.0;
            for _ in 0..n_steps {
                let z: f64 = rng.sample(StandardNormal);
                s *= (drift + vol * z).exp();
                total += s;
            }
            (total / n_steps as f64 - k).max(0.0)
        })
        .sum();
    Ok((-r * t).exp() * payoff_sum / n_paths as f64)
```

```py
    """
```

Performance comparison (daily steps over one year, i.e. 252 steps per path, python 3.13 on 22 cores):

N | numpy+threads (ms) | rust+rayon (ms) | speedup
-:|--------:|--------:|--------:
100000 | 60.6 | 23.1 | 162%
300000 | 174.7 | 67.7 | 158%
1000000 | 545.9 | 227.7 | 140%

Peak memory tells a starker story than wall-clock time. Both implementations share the same ~49MB
baseline (interpreter + numpy + xenoform_rs import); measured from there, one grows linearly with
`n_paths` and the other barely moves (linux, python 3.13):

N | numpy+threads (MB) | rust+rayon (MB)
-:|--------:|--------:
100000 | 241.2 | 49.5
300000 | 625.1 | 49.8
1000000 | 1972.3 | 50.1

`rust+rayon`'s peak never rises meaningfully above the baseline - each path lives in a register, and
the only heap growth left is rayon's fixed per-thread stacks. `numpy+threads` grows in lock-step with
`n_paths × n_steps × 8 bytes`, because the vectorised implementation must materialise the whole matrix
(see above) - ~39x more memory than rust at a million paths. Peak RSS was read via
`resource.getrusage(RUSAGE_SELF).ru_maxrss` (KiB on linux, bytes on macOS), each implementation
measured in its own fresh subprocess: `ru_maxrss` is a process-lifetime high-water mark that never
decreases, so profiling both variants in one process would leak whichever ran first (typically
numpy's ~2GB) into the second implementation's reading. This was a one-off local measurement, not a
script wired into the example or CI.

**Why free-threading (`3.14t`) barely changes the performance numbers** - a result that surprises people expecting the
free-threaded build to be the enabler here. Free-threading only helps when the GIL is what stops threads running
in parallel, and for this workload it never was:

- The rust runs the entire loop in compiled code with the GIL released (`py=False`, no python objects touched), so
  its parallelism was never GIL-limited.
- numpy releases the GIL *inside* each large array operation (`standard_normal`, `cumsum`, `exp`, `mean`), holding
  it only for the negligible glue between them - so its thread pool already gets real parallelism on a plain
  GIL-enabled interpreter. You can watch all cores light up on 3.13.

So the GIL was already out of the way on both sides, and removing it entirely (`3.14t`) leaves nothing to gain.
Free-threading *would* matter for a **pure-python** threaded loop, which cannot release the GIL - but the moment
the baseline is numpy rather than pure python, that advantage evaporates.

Both implementations are also reproducible: the result never depends on thread scheduling, because each path's
(or shard's) random draws are pinned by its index, not by which thread happens to compute it.

Full code is in [examples/monte_carlo.py](examples/monte_carlo.py).

### Levenshtein distance

This example computes the edit distance from a query word to every word in a wordlist, using the classic
Wagner-Fischer dynamic-programming recurrence. Unlike the numeric examples above, there's no vectorised numpy
alternative here - the recurrence is over strings, one character comparison at a time - so this compares plain
python against inline rust, and shows the win isn't limited to numeric code:

```py
def levenshtein_py(a: str, b: str) -> int:
    "Wagner-Fischer edit distance: O(len(a) * len(b)) time, O(min(len(a), len(b))) space via a rolling row"
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def levenshtein_distances_py(query: str, wordlist: list[str]) -> list[int]:
    "Edit distance from query to every word in wordlist"
    return [levenshtein_py(query, w) for w in wordlist]
```

The rust version is the same algorithm, one word at a time. It also demonstrates two ends of the default type
mapping: `list[str]` and the return type `list[int]` translate to `Vec<String>`/`Vec<i32>` with no annotation
needed, while `query` is overridden to `&str` (via `Annotated`) to borrow rather than clone the one string
compared against every word:

```py
@rust(py=False, profile={"strip": "symbols"})
def levenshtein_distances_rust(
    query: Annotated[str, "&str"], wordlist: list[str]
) -> list[int]:
    """
```

```rs
    let qb = query.as_bytes();
    Ok(wordlist
        .iter()
        .map(|w| {
            let wb = w.as_bytes();
            let (long, short) = if qb.len() >= wb.len() { (qb, wb) } else { (wb, qb) };
            let mut prev: Vec<usize> = (0..=short.len()).collect();
            for (i, &lc) in long.iter().enumerate() {
                let mut curr = vec![0usize; short.len() + 1];
                curr[0] = i + 1;
                for (j, &sc) in short.iter().enumerate() {
                    let cost = usize::from(lc != sc);
                    curr[j + 1] = (curr[j] + 1).min(prev[j + 1] + 1).min(prev[j] + cost);
                }
                prev = curr;
            }
            prev[short.len()] as i32
        })
        .collect())
```

```py
    """
```

Performance comparison (synthetic lowercase wordlist, word lengths 3-12, python 3.14):

N | py (ms) | rust (ms) | speedup
-:|--------:|----------:|-----------:
1000 | 7.0 | 0.3 | 2570%
10000 | 68.2 | 2.3 | 2808%
100000 | 672.3 | 22.6 | 2872%
1000000 | 6867.8 | 235.9 | 2811%

Both allocate a fresh DP row per character of the longer string in each comparison - the rust version isn't
hand-optimised beyond the python baseline's own allocation pattern, so the ~29x speedup is purely the win from
running the same algorithm compiled rather than interpreted, not from a smarter algorithm or less allocation.

Full code is in [examples/levenshtein.py](examples/levenshtein.py).

## Type Translations

### Default mapping

Basic Python types are recursively mapped to rust types, like so:

Python | rust
------ | ---
`None` | `()`
`int` | `i32`
`np.int32` | `i32`
`np.int64` | `i64`
`bool` | `bool`
`float` | `f64`
`np.float32` | `f32`
`np.float64` | `f64`
`complex` | `&Bound<'py, PyComplex>`
`np.complex128` | `&Bound<'py, PyComplex>`
`str` | `String`
`np.ndarray` | `PyReadonlyArrayDyn`
`bytes` | `&'py [u8]`
`bytearray` | `&Bound<'py, PyByteArray>`
`list` | `Vec`
`set` | `HashSet`
`frozenset` | `HashSet`
`dict` | `HashMap`
`tuple` | `(...)`
`slice` | `&Bound<'py, PySlice>`
`Any` | `&Bound<'py, PyAny>`
`Self` | `&Bound<'py, PyAny>`
`type` | `&Bound<'py, PyType>`
`*args` | `&Bound<'py, PyTuple>`
`**kwargs` | `Option<&Bound<'py, PyDict>>`
`T \| None` | `Option<T>`
`Callable` | `&Bound<'py, PyCFunction>`
`...` | `&Bound<'py, PyEllipsis>`

Thus, `dict[str, list[float]]` becomes - by default - `HashMap<String, Vec<f64>>`.

The only type mapped to something mutable is `npt.NDArray` (`PyReadonlyArrayDyn` elements *are* mutable). For `dict`,
`list`, `set` or `bytearray` override to the corresponding pyo3 type, e.g. `PyList` (see
[test_inplace.py](src/test/test_inplace.py)).

The defaults can be overridden if necessary using the `Annotated` type, e.g.:

```py
@rust(py=False)
def fibonacci(n: Annotated[int, "u64"]) -> Annotated[int, "u64"]
    ...
```

Note:

- return types are wrapped in `PyResult<>` allowing for exceptions to be raised via `Err(...)`. See e.g.
[test_slice.py](src/test/test_slice.py)
- any `&Bound<...>` pyo3 type in the return value (even overridden) will have the reference stripped.

## Callable Types

Passing and returning functions to and from rust is supported, and they can be used interchangeably with python functions
and lambdas.

Annotate types using `Callable[...]` - this gets mapped to `Bound<'py, PyCFunction>`. When returning functions, note that pyo3's `PyCFunction` type does not intrinsically contain information about the function's argument and return types.

For function arguments, the default mapping (to `Bound<'py, PyCFunction>`) does not support python functions/lambdas.
For this reason, use the generic override `&Bound<'py, PyAny>` (`PyAnyMethods` implement the call... traits). This
example will work with both python and rust functions:

```py
@rust(py=False)
def use_modulo(func: Annotated[Callable[[int], int], "&Bound<'py, PyAny>"], i: int) -> int:
    """
    func.call1((i,))?.extract::<i32>()
    """
```

See the examples in [test_callable.py](src/test/test_callable.py) for more detail.

## Configuration

### `pyo3` version

The `pyo3` version can be overridden with the environment variable `XENOFORM_RS_PYO3_VERSION`. The default - and only supported version - is currently 0.28. Using a different version is not guaranteed to work, and will probably require overrides for all argument and return types.

### Location of Extension Modules

By default, compiled modules are placed in an `ext` subdirectory of your project's root. If this location is unsuitable,
it can be overridden using the environment variable `XENOFORM_RS_EXTMODULE_ROOT`. NB avoid using characters in paths
(e.g. space, hyphen) that would not be valid in a python module name.

### Verbose logging

Setting the environment variable `XENOFORM_RS_VERBOSE` (to any value, including empty, e.g.
`XENOFORM_RS_VERBOSE=`) turns on INFO-level logging of the compile/check/import steps, with timings. This
configures xenoform-rs's own logger only - it never touches `logging.basicConfig`/the root logger, so it
won't interfere with a host application's own logging setup.

### Free-threaded Interpreter

By default, if the interpreter is free-threaded, extension modules will be built without the GIL. This requires the extension code to be threadsafe. If xenoform detects an environment variable `XENOFORM_RS_DISABLE_FT`, free-threading is
disabled.

## Troubleshooting

The generated module source code is written to `src/lib.rs` in a module-specific folder (e.g. `ext/my_module_ext`).
Cargo build output is redirected to `build.log` in the that folder. The actual binary will be found in the
`target/release` subfolder.

Setting `XENOFORM_RS_VERBOSE=1` logs the steps taken, with timings, e.g.:

```txt
$ uv run examples/loop.py
08:34:22.535 INFO     registering loop_rs_ext.loop_rs.calc_balances_rust (in ext)
08:34:22.597 INFO     module is up-to-date (d4c7165ade6f52c0aa2ef748c4d6e7c4edce201788a65e7b6e29ebde0d480e3e)
08:34:22.597 INFO     imported compiled module loop_rs
08:34:22.598 INFO     redirected calc_balances_rust to compiled function loop_rs._calc_balances_rust
```
