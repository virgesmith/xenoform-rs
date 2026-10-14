import math
from typing import Annotated

import numpy as np
import pytest

from xenoform_rs import CompilationError, RustConfigError, RustTypeError, rust
from xenoform_rs.compile import _parse_constant, _translate_constants
from xenoform_rs.rustmodule import FunctionSpec, ModuleSpec
from xenoform_rs.utils import translate_constant

from .other_module import BIG

MAGIC_NUMBER = 19937
SCALE = 0.5
GREETING = 'say "hi"\\'
ENABLED = True
# the annotation is NOT used to type the constant -- only the "NAME: type" entry does that, see
# test_annotations_are_ignored
OFFSET: Annotated[int, "u8"] = 7


@rust(py=False, constants=["MAGIC_NUMBER", "SCALE"])
def add_magic(n: int) -> float:  # ty: ignore[empty-body]
    """
    Ok(((n + MAGIC_NUMBER) as f64) * SCALE)
    """


# MAGIC_NUMBER is declared again (identically) and GREETING is only declared here, but all are module-level
@rust(py=False, constants=["MAGIC_NUMBER", "GREETING", "ENABLED"])
def describe() -> str:  # ty: ignore[empty-body]
    """
    Ok(format!("{GREETING} {MAGIC_NUMBER} {ENABLED} {SCALE}"))
    """


# BIG is imported: found by name all the same, and typed by the entry, since its annotation stays in other_module
@rust(py=False, constants=["BIG: u64", "OFFSET:u8"])
def overridden() -> Annotated[tuple[int, int], "(u64, u8)"]:  # ty: ignore[empty-body]
    """
    Ok((u64::MAX - BIG, OFFSET.wrapping_add(250)))
    """


class Holder:
    STEP = 3

    # found in the class body, where the decorator is applied
    @staticmethod
    @rust(py=False, constants=["STEP: u8"])
    def step() -> int:  # ty: ignore[empty-body]
        """
        Ok(STEP as i32 * 2)
        """


def test_constants_are_usable_in_rust() -> None:
    assert add_magic(1) == (1 + MAGIC_NUMBER) * SCALE


def test_constants_are_module_level() -> None:
    assert describe() == f"{GREETING} {MAGIC_NUMBER} true {SCALE}"


def test_typed_constants() -> None:
    assert overridden() == (2**64 - 1 - BIG, 1)


def test_class_attribute_constant() -> None:
    assert Holder.step() == 6


def test_local_constant_shadows_global() -> None:
    MAGIC_NUMBER = -1  # noqa: N806

    @rust(py=False, module_name="test_constants_local", constants=["MAGIC_NUMBER"])
    def local_magic() -> int:  # ty: ignore[empty-body]
        "Ok(MAGIC_NUMBER)"

    assert local_magic() == MAGIC_NUMBER


def test_annotations_are_ignored() -> None:
    """Neither an imported variable's annotation (in other_module) nor a local one is consulted: the default applies"""
    assert _translate_constants(["BIG", "OFFSET"], globals()) == [
        "const BIG: i32 = 1099511627776;",
        "const OFFSET: i32 = 7;",
    ]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("X", ("X", None)),
        ("X: u64", ("X", "u64")),
        ("X:u64", ("X", "u64")),
        ("  X  :  [i32; 3] ", ("X", "[i32; 3]")),
        ("X: std::primitive::u64", ("X", "std::primitive::u64")),
    ],
)
def test_parse_constant(entry: str, expected: tuple[str, str | None]) -> None:
    assert _parse_constant(entry) == expected


@pytest.mark.parametrize("entry", ["X:", "X: "])
def test_parse_constant_missing_type(entry: str) -> None:
    with pytest.raises(RustConfigError, match="Missing rust type for constant 'X'"):
        _parse_constant(entry)


@pytest.mark.parametrize("name", ["not valid", "1X", "type", "fn"])
def test_invalid_constant_name(name: str) -> None:
    with pytest.raises(RustConfigError, match=f"Invalid constant name: '{name}'"):

        @rust(py=False, constants=[f"{name}: i32"])
        def f() -> None:
            "Ok(())"


def test_unknown_constant() -> None:
    with pytest.raises(RustConfigError, match="Constant 'MISSING' not found"):

        @rust(py=False, constants=["MISSING"])
        def f() -> None:
            "Ok(())"


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
def test_translate_typed_constant(value: object, rust_type: str, expected: str) -> None:
    assert translate_constant("X", value, rust_type) == expected


@pytest.mark.parametrize("value", [None, np.float16(1), np.bool_(True)])
def test_translate_constant_unsupported_type(value: object) -> None:
    with pytest.raises(RustTypeError, match="Don't know a Rust type"):
        translate_constant("X", value)


def test_conflicting_constants_fail_to_compile() -> None:
    """The value is captured when the decorator is applied, so reassigning K gives two different definitions"""
    K = 1  # noqa: N806

    @rust(py=False, module_name="test_constants_conflict", constants=["K"])
    def f() -> int:  # ty: ignore[empty-body]
        "Ok(K)"

    K = 2  # noqa: F841, N806 -- only read by the decorator, from the frame

    @rust(py=False, module_name="test_constants_conflict", constants=["K"])
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
    test_typed_constants()
    test_class_attribute_constant()
