import json
from pathlib import Path

import pytest

from xenoform_rs import CompilationError, RustDiagnostic, rust
from xenoform_rs.compile import _brief, _parse_cargo_messages, _select


def test_compile_error_reports_rustc_diagnostics() -> None:
    @rust(py=False)
    def add_str(i: int) -> int:  # ty: ignore[empty-body]
        """
        Ok(i + "one")
        """

    @rust(py=False)
    def wrong_return(i: int) -> int:  # ty: ignore[empty-body]
        """
        Ok(i as i64)
        """

    with pytest.raises(CompilationError) as excinfo:
        add_str(1)

    # every error is reported, not just the first (sorted, as rustc's emission order isn't part of the contract)
    diagnostics = sorted(excinfo.value.diagnostics, key=lambda d: d.code or "")
    assert [d.code for d in diagnostics] == ["E0277", "E0308"]
    assert all(d.level == "error" for d in diagnostics)
    # paths are platform-native, e.g. src\lib.rs on Windows
    assert all(d.file and Path(d.file) == Path("src/lib.rs") and d.line is not None for d in diagnostics)
    assert diagnostics[0].message == "cannot add `&str` to `i32`"
    assert diagnostics[1].message == "mismatched types"
    # rustc suggests e.g. `.try_into().unwrap()` for the narrowing conversion, but has no fix for adding a string
    assert [d.has_suggestion for d in diagnostics] == [False, True]

    # the exception text is rustc's own rendered output, for the error with a suggested fix only...
    message = str(excinfo.value)
    assert "error[E0308]: mismatched types" in message
    assert "Ok(i as i64)" in message
    assert "E0277" not in message
    assert "...and 1 more error, see" in message
    assert "build.log" in message

    # ...and shortened to the parts that refer to the generated code: sub-diagnostics pointing into std are dropped,
    # but they remain in the full rendered text (and build.log)
    def files(text: str) -> list[Path]:
        return [
            Path(line.split()[1].rsplit(":", 2)[0])
            for line in text.splitlines()
            if line.lstrip().startswith(("-->", ":::"))
        ]

    assert all(f == Path("src/lib.rs") for f in files(message))
    assert any(f != Path("src/lib.rs") for d in diagnostics for f in files(d.rendered))


_RENDERED = """\
error[E0308]: mismatched types
   --> src/lib.rs:28:12
    |
 28 |         Ok(y)
    |         -- ^ expected `i32`, found `i64`
    |
    = help: the following other types implement trait `From<T>`:
              `i32` implements `From<bool>`
              `i32` implements `From<i16>`
    = note: expected type `i32`
               found type `i64`
    = help: a one-line hint
note: tuple variant defined here
   --> STD_PATH:562:5
    |
562 |     Ok(T),
    |     ^^
note: required by a bound in `TryInto`
   --> /rustc/0123456789abcdef/library/core/src/convert/mod.rs:604:1
help: you can convert an `i64` to an `i32` and panic if the converted value doesn't fit
    |
 28 |         Ok(y.try_into().unwrap())
    |             ++++++++++++++++++++

"""

# an absolute path on the platform running the test (i.e. with a drive on Windows), as reported when the rust-src
# component is installed. Without it, std paths are remapped to "/rustc/<hash>/...", which is rooted but has no drive
_STD_PATH = str(Path.home() / ".rustup" / "core" / "src" / "result.rs")


def test_brief_drops_help_lists_and_sub_diagnostics_outside_the_crate() -> None:
    assert _brief(_RENDERED.replace("STD_PATH", _STD_PATH)) == "\n".join(
        [
            "error[E0308]: mismatched types",
            "   --> src/lib.rs:28:12",
            "    |",
            " 28 |         Ok(y)",
            "    |         -- ^ expected `i32`, found `i64`",
            "    |",
            # the multi-line "= help:" list is dropped, but multi-line notes and one-line hints are kept
            "    = note: expected type `i32`",
            "               found type `i64`",
            "    = help: a one-line hint",
            # both std "note"s are dropped, including the "562 | ..." line, which starts at column 0 like a header would
            "help: you can convert an `i64` to an `i32` and panic if the converted value doesn't fit",
            "    |",
            " 28 |         Ok(y.try_into().unwrap())",
            "    |             ++++++++++++++++++++",
        ]
    )


def _compiler_message(**message: object) -> str:
    return json.dumps({"reason": "compiler-message", "message": message})


def test_parse_cargo_messages_reads_only_compiler_messages() -> None:
    error = _compiler_message(
        level="error",
        code={"code": "E0308", "explanation": "..."},
        message="mismatched types",
        rendered="error[E0308]: mismatched types\n",
        spans=[{"file_name": "src/lib.rs", "line_start": 28, "is_primary": True}],
        children=[{"level": "help", "spans": [{"suggested_replacement": "y.try_into().unwrap()"}]}],
    )
    # e.g. linker failures have no source location
    spanless = _compiler_message(
        level="error", code=None, message="linking failed", rendered="error: linking failed\n", spans=[], children=[]
    )
    stdout = "\n".join(
        [
            "not JSON",
            json.dumps({"reason": "compiler-artifact"}),
            error,
            spanless,
            json.dumps({"reason": "build-finished", "success": False}),
        ]
    )
    assert _parse_cargo_messages(stdout) == [
        RustDiagnostic(
            level="error",
            code="E0308",
            message="mismatched types",
            rendered="error[E0308]: mismatched types\n",
            file="src/lib.rs",
            line=28,
            has_suggestion=True,
        ),
        RustDiagnostic(level="error", code=None, message="linking failed", rendered="error: linking failed\n"),
    ]


def _error(code: str, *, has_suggestion: bool = False) -> RustDiagnostic:
    return RustDiagnostic(level="error", code=code, message="", rendered="", has_suggestion=has_suggestion)


def test_select_prefers_errors_with_a_suggested_fix() -> None:
    # typically the knock-on errors come first and the root cause, carrying the fix, last
    errors = [
        _error("E0271"),
        _error("E0308", has_suggestion=True),
        _error("E0277"),
        _error("E0599", has_suggestion=True),
    ]
    assert [e.code for e in _select(errors)] == ["E0308", "E0599"]


def test_select_falls_back_to_the_first_error() -> None:
    assert [e.code for e in _select([_error("E0271"), _error("E0277")])] == ["E0271"]


if __name__ == "__main__":
    test_compile_error_reports_rustc_diagnostics()
    test_brief_drops_help_lists_and_sub_diagnostics_outside_the_crate()
    test_parse_cargo_messages_reads_only_compiler_messages()
    test_select_prefers_errors_with_a_suggested_fix()
    test_select_falls_back_to_the_first_error()
