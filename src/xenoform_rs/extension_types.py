# dummy generic types for references and pointers
from collections.abc import Callable
from types import NoneType, UnionType
from typing import Annotated, Any, Self, get_args, get_origin

import numpy as np

from xenoform_rs.errors import RustTypeError

DEFAULT_TYPE_MAPPING = {
    None: "()",  # py::none?
    int: "i32",
    np.int32: "i32",
    np.int64: "i64",
    bool: "bool",
    float: "f64",
    # complex: "std::complex<double>",
    np.float32: "f32",
    np.float64: "f64",
    # complex: "std::complex<double>",
    # np.complex64: "std::complex<float>",
    # np.complex128: "std::complex<double>",
    np.ndarray: "PyReadonlyArrayDyn",
    str: "String",  # or "&'py str"?
    bytes: "&'py [u8]",  # or Vec<u8>?
    bytearray: "Vec<u8>",
    list: "Vec",
    set: "HashSet",
    frozenset: "HashSet",
    dict: "HashMap",
    tuple: "tuple_placeholder",  # this gets replaced with rust's tuple syntax ... ellipsis not supported here
    # slice: "py::slice",
    Any: "Bound<'py, PyAny>",
    Self: "Bound<'py, PyAny>",
    type: "Bound<'py, PyType>",
    UnionType: "Option",
    Callable: "Bound<'py, PyCFunction>",  # override function arguments to Bound<'py, PyAny> to pass python functions/lambdas to rust
    # EllipsisType: "py::ellipsis",
}


class PyTypeTree:
    """Tree structure for python types"""

    def __init__(self, type_: type) -> None:
        origin = get_origin(type_)
        if origin is Annotated:
            raise TypeError("Don't pass annotated types directly to PyTypeTree, use translate_type")

        self.type = origin if origin is not None else type_

        if self.type is Callable:
            # flatten args, put ret first
            args, ret = get_args(type_)
            self.subtypes = (PyTypeTree(ret), *(PyTypeTree(a) for a in args))
        else:
            self.subtypes = tuple(PyTypeTree(t) for t in get_args(type_))

    def __repr__(self) -> str:
        if self.type == Ellipsis:
            return "..."
        if self.subtypes:
            return f"{self.type.__name__}[{', '.join(repr(t) for t in self.subtypes)}]"
        return f"{self.type.__name__}"


class RustTypeTree:
    """Mapped tree structure for Rust types"""

    def __init__(self, tree: PyTypeTree, *, override: str | None = None) -> None:
        self.type = DEFAULT_TYPE_MAPPING.get(tree.type)  # type: ignore[arg-type]
        if not self.type and not override:
            raise RustTypeError(f"Don't know a Rust type for '{tree.type}' and no override provided")
        self.override = override
        if tree.type == np.ndarray:
            self.subtypes: tuple[RustTypeTree, ...] = (RustTypeTree(tree.subtypes[1].subtypes[0]),)
        elif tree.type == Callable:
            # pyo3 doesn't support typing callable objects
            self.subtypes: tuple[RustTypeTree, ...] = ()
        else:
            self.subtypes = tuple(RustTypeTree(t) for t in tree.subtypes if t.type is not NoneType)
        if self.type == "Option" and len(self.subtypes) == len(tree.subtypes) - 1 and len(self.subtypes) > 1:
            raise TypeError(
                "variant types are not currently supported, use '&Bound<'_, PyAny>' as an override rust type"
            )

    def __repr__(self) -> str:
        if self.override:
            return self.override
        t = f"{self.type}"
        if self.type == "std::function":
            t = t + f"<{self.subtypes[0]}({', '.join(repr(t) for t in self.subtypes[1:])})>"
        elif self.subtypes:
            t = t + f"<{', '.join(repr(t) for t in self.subtypes)}>"
        return t


def parse_annotation(origin: type) -> tuple[type, dict[str, str]]:
    """
    Extract content from Annotation, if present. optional 2nd return value can bbe used as kwargs
    """
    t = get_origin(origin)
    if t is None and get_args(origin):
        raise RustTypeError("Python types with no default mapping must be annotated with a type override")
    if t is Annotated:
        base, *extras = get_args(origin)
        assert len(extras) == 1, "one and only one annotation must be specified"
        if isinstance(extras[0], str):
            return base, {"override": extras[0]}
        raise TypeError(f"Unexpected extra for {base}: {extras[0]}({type(extras[0])})")
    return origin, {}


def translate_type(t: type) -> RustTypeTree:
    """
    Covert a python type to a string representing the Rust equivalent
    using the default mappings defined in default_type_mapping
    """

    base_type, extras = parse_annotation(t)
    return RustTypeTree(PyTypeTree(base_type), **extras)
