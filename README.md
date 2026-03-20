# xenoform-rs

**[Work-in-progress]** A rust-flavoured version of [xenoform](https://pypi.org/project/xenoform/), which will likely be functionally less
complete than its C++ sister.

- [X] `numpy` array support
- [X] positional and keyword arguments and markers
- [X] *args/**kwargs
- [X] type overrides via `Annotated`
- [X] callable types (partial). See below.
- [X] free-threaded execution
- [ ] auto-vectorisation
- [ ] link to external libs
- [ ] ~~compound types~~ (rust doesn't support this)


Notes:

- callable types:
    - typed functions/closures are not supported.
    - default type mapping (`Callable` -> `Bound<'py, PyCFunction>`) works for return values but doesn't allow for python functions/lambdas to be passed into rust. In this case override to `Bound<'py, PyAny>` (`PyAnyMethods` implement the call... traits).
- complex: 128 bit support only (i.e. not `np.complex64`)

## Performance

See [the (C++) xenoform version](https://github.com/virgesmith/xenoform/blob/main/README.md#performance) for context.

### Loop

```py
@rust(
    extra_deps=['numpy = { version = "0.28" }'],
    extra_uses=[
        "use numpy::{PyArray1, PyArrayMethods};",
        "use pyo3::types::{PyDict, PyAnyMethods};",
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
    let data_np = data.call_method0("to_numpy")?;
    let data_a: &Bound<'py, PyArray1<i64>> = data_np.cast()?;
    let a = unsafe { data_a.as_array() };
    let n = a.len();

    let mut r = vec![0.0; n];
    let mut current_value = 0.0;

    for i in 0..n {
        current_value = (current_value + a[i] as f64) * (1.0 - rate);
        r[i] = current_value;
    }

    // Construct a pd.Series with the same index as the input
    let result_np = PyArray1::from_slice(py, &r);
    let kwargs = PyDict::new(py);
    kwargs.set_item("index", data.getattr("index")?)?;

    let pd = py.import("pandas")?;
    let result = pd.getattr("Series")?.call((result_np,), Some(&kwargs))?;

    Ok(result)
```

```py
    """
```

N | py (ms) | rust (ms) | speedup (%)
-:|--------:|---------:|-----------:
1000 | 0.3 | 1.3 | -79
10000 | 1.1 | 0.1 | 867
100000 | 12.5 | 1.1 | 1085
1000000 | 115.1 | 6.0 | 1832
10000000 | 1134.6 | 43.8 | 2488

For reference, the xenoform implementation is twice as fast.

### Distance Matrix

```py
@rust(
    extra_deps=['numpy = { version = "0.28" }'],
    extra_uses=["use numpy::{PyArray2, PyArrayMethods, PyReadonlyArray2};"],
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


N | py (ms) | rust (ms) | speedup (%)
-:|--------:|----------:|-----------:
100 | 0.7 | 1.5 | -54%
300 | 3.4 | 0.1 | 2838%
1000 | 30.2 | 1.3 | 2246%
3000 | 204.8 | 19.1 | 972%
10000 | 2794.9 | 209.8 | 1232%

For reference, this is  *five times faster* than the xenoform implementation with openmp optimisations!
