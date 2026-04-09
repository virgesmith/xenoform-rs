from xenoform_rs import rust
from xenoform_rs.compile import _get_function
from xenoform_rs.rustmodule import _format_help

docstr = """This is a test function
used to test the help system
It is otherwise useless"""


def test_help_format() -> None:
    assert (
        _format_help(docstr)
        == R"""/// This is a test function
/// used to test the help system
/// It is otherwise useless"""
    )


@rust(py=False, help=docstr, verbose=True)
def documented_function(n: int, *, x: float = 3.1) -> float:  # ty: ignore[empty-body]
    """
    Ok(n as f64 + x)
    """


def test_documented_function() -> None:
    assert documented_function.__doc__ == docstr
    # access rust module directly
    ext_func = _get_function("test_help", "_documented_function")

    assert docstr in (ext_func.__doc__ or "")


if __name__ == "__main__":
    test_help_format()
    test_documented_function()
