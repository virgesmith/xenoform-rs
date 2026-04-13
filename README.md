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

When Python loads this module, all functions using this decorator have their function signatures translated to rust
and the source for an extension module with python bindings is generated. The first time any function is called, the
module is built, the attribute corresponding to the (empty) Python function is replaced with the rust implementation in
the module.

Subsequent calls to these functions incur minimal overhead, as the attribute corresponding to the (dummy) python function
already points to the rust implementation.

Each module stores a hash of its source code (and Cargo.toml). Modules are checked on load and automatically rebuilt
when any changes are detected.

By default, the binaries, source code and build logs for the compiled modules can be found in the `ext` subfolder (this
location can be changed).

## Features

- Supports `numpy` arrays (via the `numpy` crate) for customised "vectorised" operations.
- By [default](#free-threaded-interpreter), supports parallel execution when the python interpreter is free-threaded.
- Supports positional and keyword arguments with defaults, including positional-only and keyword-only markers (`/`,`*`)
- Supports `*args` and `**kwargs`, mapped  (respectively) to `&Bound<'py, PyTuple>` and `Option<&Bound<'py, PyDict>>`.
NB type annotations for these types are still useful for python type checkers. See [test_kwargs.py](src/test/test_kwargs.py)
- Supports custom dependencies and imports.
- Using annotated types, you can override the default mapping of python types to rust types, or pass types
- Callable types are supported both as arguments and return values. See [below](#callable-types).
- Optional (`T | None`) types are supported, mapping to `Option<T>`
- Can link to separate rust sources, see [test_modules.py](src/test/test_modules.py) for details.

Caveats & points to note:

- callable types (more detail [here](#callable-types)):
    - only generic (untyped) functions/closures are supported.
    - the default type mapping (`Callable` -> `Bound<'py, PyCFunction>`) works for return values but not for arguments.
- complex: 128 bit support only (i.e. not `np.complex64`)
- if additional modules are specified, the files are copied into the crate. Modifications to additional modules will
trigger a rebuild.
- compound/variant types: only optional (`T | None`) is supported. Use a type override to a generic python type e.g.
`Annotated[int | float, "&Bound<'py, PyAny>"]` or coerce to a single rust type e.g. `Annotated[int | float, "f64"]`.
- no support currently for linking to external prebuilt binaries
- no support for compound types (would require building support for rust enums)
- due to restrictions arising from linguistic differences, xenoform-rs will likely never be as functionally complete
than its C++ sister, [xenoform](https://pypi.org/project/xenoform/)

## Getting started

Install the package

```sh
uv add xenoform-rs  # or use pip
```

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
    # the return type is a rust usize converted to a python int
    """
    Ok(a.as_array().shape().iter().product())
    """


print(array_nelems(np.empty([2, 3, 5, 7], dtype=np.int64)))
```

## Decorator parameters

name | type | default | description
---- | ---- | ------- | -----------
`py` | `bool` | `True` | Pass the python context as the first argument. Necessary when (e.g.) creating python objects.
`dependencies` | `list[str] \| None` | `None` | Rust package dependencies, the `rust_dependency` convenience function can be used to specify dependency parameters, e.g. `dependencies=[rust_dependency("numpy", version="0.28")]`.
`imports` | `list[str] \| None` | `None` | Additional imports, e.g. `imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"]`
`modules` | `list[Path \| str] \| None` | `None` | Sources for additional modules
`edition` | `str` | `"2024"` | The rust edition.
`profile` | `dict[str, str] \| None` | `None` | Overrides to (release mode) [profile](https://doc.rust-lang.org/cargo/reference/profiles.html), e.g. optimisation level, strip symbols, etc.
`help` | `str \| None` | `None` | Docstring for the function
`verbose` | `bool` | `False` | enable debug logging

## Performance

Rust can offer very significant performance enhancements over python, especially where *vectorised* &ast; operations are not available, but even when they are.

> &ast; "vectorisation" in this sense means implementing loops in compiled - rather than interpreted - code. In fact, the compiler also has various optimisations available to it including but by no means limited to "true" vectorisation (meaning hardware SIMD instructions).

The first example deals with a an operation on a pandas Series that must be done sequentially, and the second shows that significant performance gains can be had even when a vectorised python implementation is possible. Running these examples requires  the "examples" optional dependency (and of course [rust](https://rust-lang.org/tools/install/)):

```sh
pip install xenoform-rs[examples]
```

### Loop

This is a Rust vs python comparison of a non-vectorisable sequential operation on a `pd.Series`. Note that pyo3/rust knows nothing about pandas, but can still operate on such objects via their python API:

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

```py
@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArray1, PyArrayMethods}", "pyo3::types::{PyDict, PyAnyMethods}"],
    module_name="loop_rs",  # override as "loop" is a rust keyword
    profile={"strip": "symbols"},
)
def calc_balances_rust(
    data: Annotated[pd.Series, "Bound<'py, PyAny>"], rate: float
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

N | py (ms) | rust (ms) | speedup
-:|--------:|----------:|-----------:
1000 | 0.5 | 1.2 | -60%
10000 | 2.0 | 0.1 | 2235%
100000 | 18.7 | 0.5 | 3654%
1000000 | 192.8 | 2.7 | 7131%
10000000 | 1894.8 | 22.8 | 8214%

Full code is in [examples/loop.py](examples/loop.py).

### Distance Matrix

For example, to compute a distance matrix between $N$ points in $D$ dimensions, an efficient `numpy` implementation
could be:

```py
def calc_dist_matrix_py(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))
```

bearing in mind there is some redundancy here as the resulting matrix is symmetric; however vectorisation with
redundancy will always win the tradeoff against loops with no redundancy. But a rust implementation is significantly
faster, partly because it can avoid redundant computations:

```py
@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"],
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

    let result = PyArray2::zeros(py, [n, n], false);
    let mut r = unsafe { result.as_array_mut() };

    for i in 0..n {
        for j in i + 1..n {
            let mut sum = 0.0;
            for k in 0..d {
                let diff = points.get([i, k]).unwrap() - points.get([j, k]).unwrap();
                sum += diff * diff;
            }
            let dist = sum.sqrt();
            if let Some(x) = r.get_mut([i, j]) {
                *x = dist;
            }
            if let Some(x) = r.get_mut([j, i]) {
                *x = dist;
            }
        }
    }
    Ok(result)
```

```py
    """
```

N | py (ms) | rust (ms) | speedup
-:|--------:|----------:|-----------:
100 | 0.4 | 1.3 | -68%
300 | 3.6 | 0.2 | 1907%
1000 | 28.7 | 2.3 | 1162%
3000 | 208.1 | 20.8 | 902%
10000 | 2270.2 | 236.2 | 861%

Full code is in [examples/distance_matrix.py](examples/distance_matrix.py).

## Configuration

### `pyo3` version

The `pyo3` version can be overridden with the environment variable `XENOFORM_RS_PYO3_VERSION`. The default - and only supported version - is currently 0.28. Using a different version is not guaranteed to work, and may require type overrides.

### Location of Extension Modules

By default, compiled modules are placed in an `ext` subdirectory of your project's root. If this location is unsuitable,
it can be overridden using the environment variable `XENOFORM_RS_EXTMODULE_ROOT`. NB avoid using characters in paths
(e.g. space, hyphen) that would not be valid in a python module name.

### Free-threaded Interpreter

By default, if the interpreter is free-threaded, extension modules will be built without the GIL. This requires the extension code to be threadsafe. If xenoform detects an environment variable `XENOFORM_RS_DISABLE_FT`, free-threading is
disabled.


## Type Translations

### Default mapping

Basic Python types are recursively mapped to rust types, like so:

Python | rust
-------|----
`None` | `()`
`int` | `i32`
`np.int32` | `i32`
`np.int64` | `i64`
`bool` | `bool`
`float` | `f64`
`np.float32` | `f32`
`np.float64` | `f64`
`complex` | `Bound<'py, PyComplex>`
`np.complex128` | `Bound<'py, PyComplex>`
`str` | `String`
`np.ndarray` | `PyReadonlyArrayDyn`
`bytes` | `&'py [u8]`
`bytearray` | `Bound<'py, PyByteArray`
`list` | `Vec`
`set` | `HashSet`
`frozenset` | `HashSet`
`dict` | `HashMap`
`tuple` | `(...)`
`slice` | `Bound<'py, PySlice>`
`Any` | `Bound<'py, PyAny>`
`Self` | `Bound<'py, PyAny>`
`type` | `Bound<'py, PyType>`
`*args` | `&Bound<'py, PyTuple>`
`**kwargs` | `Option<&Bound<'py, PyDict>>`
`T \| None` | `Option<T>`
`Callable` | `Bound<'py, PyCFunction>`
`...` | `Bound<'py, PyEllipsis>`

Thus, `dict[str, list[float]]` becomes - by default - `HashMap<String, Vec<f64>>`.

The only type mapped to something mutable is `npt.NDArray` (`PyReadonlyArrayDyn` elements *are* mutable). For `dict`,
`list`, `set` or `bytearray` override to the corresponding pyo3 type, e.g. `PyList` (see
[test_inplace.py](src/test/test_inplace.py)).

## Callable Types

Passing and returning functions to and from rust is supported, and they can be used interchangeably with python functions
and lambdas. Annotate types using `Callable[...]` - this gets mapped to `Bound<'py, PyCFunction>`

When returning functions, note that pyo3's `PyCFunction` type does not intrinsically contain information about the
function's argument and return types.

doesn't allow for
python functions/lambdas to be passed into rust. In this case override to `Bound<'py, PyAny>` (`PyAnyMethods` implement the call... traits).

However, When passing function (either python or rust) arguments, the generic override `Bound<'py, PyAny>` should be
used - it has the necessary API - e.g.:

```py
@rust(py=False)
def use_modulo(f: Annotated[Callable[[int], int], "Bound<'py, PyAny>"], i: int) -> int:
    """
    f.call1((i,))?.extract::<i32>()
    """
```

See the examples in [test_callable.py](src/test/test_callable.py) for more detail.

## Troubleshooting

The generated module source code is written to `src/lib.rs` in a module-specific folder (e.g. `ext/my_module_ext`).
Cargo build output is redirected to `build.log` in the that folder. The actual binary will be found in the
`target/release` subfolder.

Adding `verbose=True` to the `rust(...)` decorator logs the steps taken, with timings, e.g.:

```txt
$ uv run examples/loop.py
08:34:22.535 INFO     registering loop_rs_ext.loop_rs.calc_balances_rust (in ext)
08:34:22.597 INFO     module is up-to-date (d4c7165ade6f52c0aa2ef748c4d6e7c4edce201788a65e7b6e29ebde0d480e3e)
08:34:22.597 INFO     imported compiled module loop_rs
08:34:22.598 INFO     redirected calc_balances_rust to compiled function loop_rs._calc_balances_rust
```
