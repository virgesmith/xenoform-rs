import math
from typing import Annotated, Any, Final

import numpy as np
import pytest

from xenoform_rs import CompilationError, RustConfigError, RustTypeError, rust
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import translate_constant

MAGIC_NUMBER = 19937
SCALE: Final = 0.5
GREETING = 'say "hi"\\'
BIG: Annotated[int, "u64"] = 2**40
OFFSET: "Annotated[int, 'u8']" = 7  # a string annotation, as with `from __future__ import annotations`


@rust(py=False, constants={"MAGIC_NUMBER": MAGIC_NUMBER, "SCALE": SCALE})
def add_magic(n: int) -> float:  # ty: ignore[empty-body]
    """
    Ok(((n + MAGIC_NUMBER) as f64) * SCALE)
    """


# MAGIC_NUMBER is declared again (identically) and GREETING is only declared here, but all are module-level
@rust(py=False, constants={"MAGIC_NUMBER": MAGIC_NUMBER, "GREETING": GREETING, "ENABLED": True})
def describe() -> str:  # ty: ignore[empty-body]
    """
    Ok(format!("{GREETING} {MAGIC_NUMBER} {ENABLED} {SCALE}"))
    """


# the types are overridden by the annotations of the python variables
@rust(py=False, constants={"BIG": BIG, "OFFSET": OFFSET})
def overridden() -> Annotated[tuple[int, int], "(u64, u8)"]:  # ty: ignore[empty-body]
    """
    Ok((u64::MAX - BIG, OFFSET.wrapping_add(250)))
    """


def test_constants_are_usable_in_rust() -> None:
    assert add_magic(1) == (1 + MAGIC_NUMBER) * SCALE


def test_constants_are_module_level() -> None:
    assert describe() == f"{GREETING} {MAGIC_NUMBER} true {SCALE}"


def test_constant_type_overrides() -> None:
    assert overridden() == (2**64 - 1 - BIG, 1)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, "const X: bool = true;"),
        (42, "const X: i32 = 42;"),
        (-1.5, "const X: f64 = -1.5;"),
        (1e300, "const X: f64 = 1e+300;"),
        (math.nan, "const X: f64 = f64::NAN;"),
        (math.inf, "const X: f64 = f64::INFINITY;"),
        (-math.inf, "const X: f64 = f64::NEG_INFINITY;"),
        (np.int32(7), "const X: i32 = 7;"),
        (np.int64(2**40), "const X: i64 = 1099511627776;"),
        (np.float32(0.25), "const X: f32 = 0.25;"),
        (np.float32(math.inf), "const X: f32 = f32::INFINITY;"),
        (np.float64(0.25), "const X: f64 = 0.25;"),
        ("a\\b", 'const X: &str = "a\\\\b";'),
    ],
)
def test_translate_constant(value: object, expected: str) -> None:
    assert translate_constant("X", value) == expected


@pytest.mark.parametrize(
    ("annotation", "value", "expected"),
    [
        (int, 1, "const X: i32 = 1;"),
        (Annotated[int, "u64"], 2**40, "const X: u64 = 1099511627776;"),
        (Final, 1, "const X: i32 = 1;"),
        (Final[Annotated[int, "u8"]], 1, "const X: u8 = 1;"),
        (str, "a", 'const X: &str = "a";'),
        (Annotated[str, "&'static str"], "a", 'const X: &\'static str = "a";'),
        (tuple[int, float], (1, 2.5), "const X: (i32, f64) = (1, 2.5);"),
        (Annotated[list[int], "[i32; 3]"], [1, 2, 3], "const X: [i32; 3] = [1, 2, 3];"),
    ],
)
def test_translate_annotated_constant(annotation: Any, value: object, expected: str) -> None:
    assert translate_constant("X", value, annotation) == expected


@pytest.mark.parametrize("value", [None, np.uint8(1), np.bool_(True)])
def test_translate_constant_unsupported_type(value: object) -> None:
    with pytest.raises(RustTypeError, match="Don't know a Rust type"):
        translate_constant("X", value)


@pytest.mark.parametrize("name", ["not valid", "1X", "type", "fn"])
def test_invalid_constant_name(name: str) -> None:
    with pytest.raises(RustConfigError, match=f"Invalid constant name: '{name}'"):

        @rust(py=False, constants={name: 1})
        def f() -> None:
            "Ok(())"


def test_conflicting_constants_fail_to_compile() -> None:
    @rust(py=False, module_name="test_constants_conflict", constants={"K": 1})
    def f() -> int:  # ty: ignore[empty-body]
        "Ok(K)"

    @rust(py=False, module_name="test_constants_conflict", constants={"K": 2})
    def g() -> int:  # ty: ignore[empty-body]
        "Ok(K)"

    with pytest.raises(CompilationError, match="E0428"):
        f()


def test_constant_value_change_triggers_rebuild() -> None:
    def make_spec(value: int) -> ModuleSpec:
        function = FunctionSpec(name="f", body="() -> PyResult<i32> { Ok(K) }", py=False, arg_annotations="", scope=())
        return ModuleSpec().add_function(function, constants=[translate_constant("K", value)])

    _, code1, hash1 = make_spec(1).make_source("m")
    _, code2, hash2 = make_spec(2).make_source("m")
    assert "const K: i32 = 1;" in code1
    assert "const K: i32 = 2;" in code2
    assert hash1 != hash2


if __name__ == "__main__":
    test_constants_are_usable_in_rust()
    test_constants_are_module_level()
    test_constant_type_overrides()
