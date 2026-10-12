import math
from typing import Annotated

import numpy as np
import pytest

from xenoform_rs import CompilationError, RustConfigError, RustConstant, RustTypeError, rust, rust_constant
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import translate_constant

from .other_module import BIG

MAGIC_NUMBER = 19937
SCALE = 0.5
GREETING = 'say "hi"\\'
# the annotation is NOT used to type the constant -- only rust_constant does that, see test_annotations_are_ignored
OFFSET: Annotated[int, "u8"] = 7


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


# BIG is imported, so no annotation could type it here: rust_constant can
@rust(py=False, constants={"BIG": rust_constant(BIG, "u64"), "OFFSET": rust_constant(OFFSET, "u8")})
def overridden() -> Annotated[tuple[int, int], "(u64, u8)"]:  # ty: ignore[empty-body]
    """
    Ok((u64::MAX - BIG, OFFSET.wrapping_add(250)))
    """


def test_constants_are_usable_in_rust() -> None:
    assert add_magic(1) == (1 + MAGIC_NUMBER) * SCALE


def test_constants_are_module_level() -> None:
    assert describe() == f"{GREETING} {MAGIC_NUMBER} true {SCALE}"


def test_rust_constant_types() -> None:
    assert overridden() == (2**64 - 1 - BIG, 1)


def test_annotations_are_ignored() -> None:
    """Neither an imported variable's annotation (in other_module) nor a local one is consulted: the default applies"""
    assert translate_constant("BIG", BIG) == "const BIG: i32 = 1099511627776;"
    assert translate_constant("OFFSET", OFFSET) == "const OFFSET: i32 = 7;"


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
        (np.int8(-7), "const X: i8 = -7;"),
        (np.int16(-7), "const X: i16 = -7;"),
        (np.int32(7), "const X: i32 = 7;"),
        (np.int64(2**40), "const X: i64 = 1099511627776;"),
        (np.uint8(255), "const X: u8 = 255;"),
        (np.uint16(7), "const X: u16 = 7;"),
        (np.uint32(7), "const X: u32 = 7;"),
        (np.uint64(2**63), "const X: u64 = 9223372036854775808;"),
        (np.float32(0.25), "const X: f32 = 0.25;"),
        (np.float32(math.inf), "const X: f32 = f32::INFINITY;"),
        (np.float64(0.25), "const X: f64 = 0.25;"),
        ("a\\b", 'const X: &str = "a\\\\b";'),
    ],
)
def test_translate_constant(value: object, expected: str) -> None:
    assert translate_constant("X", value) == expected


@pytest.mark.parametrize(
    ("value", "rust_type", "expected"),
    [
        (2**40, "u64", "const X: u64 = 1099511627776;"),
        (1.0, "f32", "const X: f32 = 1.0;"),
        (math.nan, "f32", "const X: f32 = f32::NAN;"),
        ("a", "&'static str", 'const X: &\'static str = "a";'),
        ((1, 2.5), "(i32, f64)", "const X: (i32, f64) = (1, 2.5);"),
        ([1, 2, 3], "[i32; 3]", "const X: [i32; 3] = [1, 2, 3];"),
        (np.uint8(1), "u32", "const X: u32 = 1;"),
    ],
)
def test_translate_rust_constant(value: object, rust_type: str, expected: str) -> None:
    assert translate_constant("X", rust_constant(value, rust_type)) == expected


def test_rust_constant() -> None:
    assert rust_constant(1, "u8") == RustConstant(1, "u8")


@pytest.mark.parametrize("rust_type", [int, np.int64, Annotated[int, "i64"]])
def test_rust_constant_needs_a_rust_type_string(rust_type: object) -> None:
    with pytest.raises(RustConfigError, match="rust_constant needs a rust type string"):
        rust_constant(1, rust_type)  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize("value", [None, np.float16(1), np.bool_(True)])
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
    test_rust_constant_types()
