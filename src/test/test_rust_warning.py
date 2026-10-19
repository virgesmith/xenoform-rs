import warnings
from pathlib import Path

import pytest

from xenoform_rs import RustWarning, rust
from xenoform_rs import compile as compile_mod


@pytest.fixture(autouse=True)
def always_rebuild(monkeypatch: pytest.MonkeyPatch) -> None:
    # warnings are only issued when cargo runs, which an up-to-date module from a previous test run would skip
    monkeypatch.setattr(compile_mod, "_read_checksum", lambda *_args: "0" * 64)


def test_rustc_warnings_are_issued_as_rust_warnings() -> None:
    @rust(py=False, module_name="warning_mod")
    def plus_one(x: int) -> int:  # ty: ignore[empty-body]
        """
        let unused = 42;
        Ok(x + 1)
        """

    with pytest.warns(RustWarning, match="unused variable: `unused`") as record:
        assert plus_one(1) == 2

    [warning] = record
    assert isinstance(warning.message, RustWarning)
    assert "warning_mod_ext" in str(warning.message)
    # the structured diagnostic is attached, as for CompilationError
    diagnostic = warning.message.diagnostic
    assert diagnostic.level == "warning"
    assert diagnostic.code == "unused_variables"
    assert diagnostic.file and Path(diagnostic.file) == Path("src/lib.rs")
    assert diagnostic.has_suggestion
    # attributed to the call that triggered the build, not to xenoform_rs internals
    assert Path(warning.filename) == Path(__file__)


def test_clean_build_issues_no_rust_warning() -> None:
    @rust(py=False, module_name="no_warning_mod")
    def plus_two(x: int) -> int:  # ty: ignore[empty-body]
        """Ok(x + 2)"""

    with warnings.catch_warnings():
        warnings.simplefilter("error", RustWarning)
        assert plus_two(1) == 3


def test_rust_warnings_can_be_treated_as_errors() -> None:
    @rust(py=False, module_name="warning_error_mod")
    def plus_three(x: int) -> int:  # ty: ignore[empty-body]
        """
        let mut y = x;
        Ok(y + 3)
        """

    # e.g. `filterwarnings = ["error::xenoform_rs.RustWarning"]` in pytest config, or -W/PYTHONWARNINGS
    with warnings.catch_warnings():
        warnings.simplefilter("error", RustWarning)
        with pytest.raises(RustWarning, match="variable does not need to be mutable"):
            plus_three(1)
