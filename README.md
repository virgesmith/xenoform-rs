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

When Python loads this file, all functions using this decorator have their function signatures translated to rust
and the source for an extension module is generated. The first time any function is called, the module is built, the attribute corresponding to the (empty) Python function is replaced with the rust implementation in the module.

Subsequent calls to the function incur minimal overhead, as the attribute corresponding to the (dummy) python function
now points to the rust implementation.

Each module stores a hash of its source code (and Cargo.toml). Modules are checked on load and
automatically rebuilt when any changes are detected.

By default, the binaries, source code and build logs for the compiled modules can be found in the `ext` subfolder (this location can be changed).

## Features

- Supports `numpy` arrays (via the `numpy` crate) for customised "vectorised" operations.
- By [default](#free-threaded-interpreter), supports parallel execution when the python interpreter is free-threaded.
- Supports positional and keyword arguments with defaults, including positional-only and keyword-only markers (`/`,`*`)
- Supports `*args` and `**kwargs`, mapped  (respectively) to `py::args` and `py::kwargs`. NB type annotations for these
types are still useful for python type checkers.
- Supports custom dependencies and imports.
- Using annotated types, you can override the default mapping of python types to rust types, or pass types
- Callable types are supported both as arguments and return values. See [below](#callable-types).
- Optional (`T | None`) types are supported, mapping to `Option<T>`
- Can link to separate rust sources, see []() for details.

Caveats & points to note:

- callable types:
    - typed functions/closures are not supported.
    - default type mapping (`Callable` -> `Bound<'py, PyCFunction>`) works for return values but doesn't allow for python functions/lambdas to be passed into rust. In this case override to `Bound<'py, PyAny>` (`PyAnyMethods` implement the call... traits).
- complex: 128 bit support only (i.e. not `np.complex64`)
- if additional modules are specified, the files are copied into the crate. Modifications to additional modules will trigger a rebuild.
- compound/variant types: only optional (`T | None`) is supported. Use a type override to a generic python type e.g. `Annotated[int | float, "&Bound<'_, PyAny>"]` or coerce to a single rust type e.g. `Annotated[int | float, "f64"]`.
- no support currently for linking to external prebuilt binaries
- no support for compound types (would require building support for rust enums)
- due to retrictions arising from linguistic differences, xenoform-rs will likely never be as functionally complete than its C++ sister, [xenoform](https://pypi.org/project/xenoform/)


## Getting started

Install the package

```sh
pip install xenoform-rs
```

```py

from xenoform_rs import rust

@rust(
    py=False # don't implicitly add the python context as the first argument

)
def add(a: int, b: int) -> int:
    """
    Ok(a + b)
    """


def append(a: list[float], b: float) -> None:

print(add(2, 2))
```





## Usage

Simply decorate your rust-implemented functions with the `rust` decorator factory - it handles all the configuration and compilation. It can be customised with these optional parameters:

kwarg | type(=default) | description
----- | -------------- | -----------
`py` | `bool = True` | Pass the python context as the first argument. Necessary when (e.g.) creating python objects.
`dependencies` | `list[str] \| None = None` | Rust package dependencies, the `rust_dependency` convenience function can be used to specify dependency parameters, e.g. `dependencies=[rust_dependency("numpy", version="0.28")]`.
`imports` | `list[str] \| None = None` | Additional imports, e.g. `imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"]`
`modules` | `list[Path \| str] \| None = None` | Sources for additional modules
`edition` | `str = "2024"` | The rust edition.
`profile` | `dict[str, str] \| None = None` | Overrides to (release mode) [profile](https://doc.rust-lang.org/cargo/reference/profiles.html), e.g. optimisation level, strip symbols, etc.
`help` | `str \| None = None` | Docstring for the function
`verbose` | `bool = False` | enable debug logging

## Performance

See [the (C++) xenoform version](https://github.com/virgesmith/xenoform/blob/main/README.md#performance) for context.

Requires the "examples" optional dependency (and [rust](https://rust-lang.org/tools/install/), of course):

```sh
uv sync --extra examples
```

### Loop

Rust vs python comparison of a non-vectorisable operation on a `pd.Series`:

```py
def calc_balances_py(data: pd.Series, rate: float) -> pd.Series:
    """Cannot vectorise, since each value is dependent on the previous value"""
    result = pd.Series(index=data.index)
    result_a = result.to_numpy()
    current_value = 0.0
    for i, value in data.items():
        current_value = (current_value + value) * (1 - rate)
        result_a[i] = current_value  # ty:ignore[invalid-assignment]
    return result


@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=[
        "numpy::{PyArray1, PyArrayMethods}",
        "pyo3::types::{PyDict, PyAnyMethods}",
    ],
    module_name="loop_rs",  # override as "loop" is a rust keyword
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
    let n = data_np.len()? as usize;

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
    let result = pd.getattr("Series")?.call((result_np,), Some(&kwargs))?;

    Ok(result)
```

```py
    """
```

N | py (ms) | rust (ms) | speedup
-:| -------:|----------:|-----------:
1000 | 0.6 | 1.9 | -68%
10000 | 1.5 | 0.1 | 1410%
100000 | 28.8 | 1.0 | 2775%
1000000 | 136.4 | 3.0 | 4496%
10000000 | 1248.0 | 25.5 | 4791%

For reference, this is about as fast as the equivalent xenoform implementation.

Full code is in [examples/loop.py](examples/loop.py).

### Distance Matrix

Rust vs python comparison of a vectorised operation on a `np.array`:

```py
def calc_dist_matrix_py(p: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    "Compute distance matrix from points, using numpy"
    return np.sqrt(((p[:, np.newaxis, :] - p[np.newaxis, :, :]) ** 2).sum(axis=2))


@rust(
    dependencies=[rust_dependency("numpy", version="0.28")],
    imports=["numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2}"],
)
def calc_dist_matrix_rust(
    points: Annotated[npt.NDArray[np.float64], "PyReadonlyArray2<f64>"],
) -> Annotated[npt.NDArray[np.float64], "Bound<'py, PyArray2<f64>>"]:  # ty: ignore[empty-body]
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
100 | 0.7 | 1.5 | -54%
300 | 3.4 | 0.1 | 2838%
1000 | 30.2 | 1.3 | 2246%
3000 | 204.8 | 19.1 | 972%
10000 | 2794.9 | 209.8 | 1232%

For reference, this is *five times faster* than the xenoform implementation, which has openmp optimisations!

Full code is in [examples/distance_matrix.py](examples/distance_matrix.py).


## Configuration

### `pyo3` version

The `pyo3` version can be overridden with the environment variable `XENOFORM_RS_PYO3_VERSION`. The default is currently 0.28.

### Location of Extension Modules

By default, compiled modules are placed in an `ext` subdirectory of your project's root. If this location is unsuitable,
it can be overridden using the environment variable `XENOFORM_RS_EXTMODULE_ROOT`. NB avoid using characters in paths
(e.g. space, hyphen) that would not be valid in a python module name.

### Free-threaded Interpreter

By default, if the interpreter is free-threaded, extension modules will be built without the GIL. This requires the
extension code to be threadsafe. If xenoform detects an environment variable `XENOFORM_RS_DISABLE_FT`, free-threading is
disabled.


## Type Translations

### Default mapping

Basic Python types are recursively mapped to C++ types, like so:

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
`*args` | `&Bound<'_, PyTuple>`
`**kwargs` | `Option<&Bound<'_, PyDict>>`
`T \| None` | `Option<T>`
`Callable` | `Bound<'py, PyCFunction>`
`...` | `Bound<'py, PyEllipsis>`




Thus, `dict[str, list[float]]` becomes - by default -  `HashMap<String, Vec<f64>>`. Also,
any C++ headers required to define the mapped type will be automatically #include'd in the module source code.

TODO By default, only `np.array` is mapped to a type that supports in-place modification. For `dict`, `list`,
or `set` map to the corresponding pybind11 type, e.g. `py::list` (see below). Note also `py::bytearray` has no mutable
methods.