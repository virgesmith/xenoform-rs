import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor

from itrx import Itr

from xenoform_rs import rust
from xenoform_rs.config import get_config


def build_freethreaded() -> bool:
    """Return whether interpreter is free-threaded AND free-threading hasn't been manually overridden"""
    if sys.version_info[1] < 13:
        return False
    return not (sys._is_gil_enabled() or get_config().disable_ft is not None)


@rust(py=False, imports=["std::{thread, time::Duration}"])
def artifically_slow_function(time: float) -> None:
    """
    let t = Duration::from_millis((time * 1000.0) as u64);
    thread::sleep(t);
    Ok(())
    """


def test_freethreaded() -> None:
    # ensure module is built by calling the function before any timing
    artifically_slow_function(0.0)

    t = 0.1
    # GIL should run sequentially (~2 * 0.1), freethreaded in parallel (~0.1, depending on available resources)
    n_threads = 2

    start = time.perf_counter()
    with ThreadPoolExecutor() as executor:
        futures = Itr(executor.submit(artifically_slow_function, t) for _ in range(n_threads))
        futures.consume()
    elapsed = time.perf_counter() - start

    if not build_freethreaded():
        assert elapsed > t * n_threads
    else:
        if elapsed >= t * n_threads:
            warnings.warn(
                f"test_freethreaded: Interpreter is free-threaded, but elapsed time is greater than expected: "
                f"Elapsed: {elapsed:.2f}, Total: {t * n_threads:.2f}. "
                "This may be a bug but could also be due to CI resource contraints.",
                stacklevel=2,
            )
        assert elapsed < t * n_threads


if __name__ == "__main__":
    print("FT?", build_freethreaded())
    test_freethreaded()
