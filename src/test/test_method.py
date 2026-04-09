from typing import Self

import pytest

from xenoform_rs import rust
from xenoform_rs.utils import get_function_scope

from .other_module import Base, ClassA


class ClassB(Base):
    X: str = "B"

    def __init__(self) -> None:
        self.x = 2

    @rust(py=False)
    def method(pyself: Self) -> int:  # ty: ignore[empty-body]  # noqa: N805
        """
        // extract instance variable
        Ok(pyself.getattr("x")?.extract::<i32>()?)
        """

    @staticmethod
    @rust(py=False)
    def static_method(i: int) -> int:  # ty: ignore[empty-body]
        """
        Ok(i + 1000)
        """

    @classmethod
    @rust(py=False, imports=["pyo3::types::PyType"])
    def class_method(cls: type) -> str:  # ty: ignore[empty-body]
        """
        // extract X from cls arg
        Ok(cls.getattr("X")?.extract::<String>()?)
        """


class ClassC(Base):
    X: str = "C"

    @rust(py=False)
    def method(_self: Self) -> int:  # ty: ignore[empty-body]  # noqa: N805
        """
        Ok(3)
        """

    @classmethod
    @rust(py=False)
    def class_method(cls: type) -> str:  # ty: ignore[empty-body]
        """
        // extract X from cls arg
        Ok(cls.getattr("X")?.extract::<String>()?)
        """


def test_function_scope() -> None:
    assert get_function_scope(ClassA.method) == ("class_a",)


def test_method() -> None:
    a = ClassA()
    b = ClassB()
    c = ClassC()

    def f(obj: Base) -> int:
        return obj.method()

    # test scope resolution works for instance methods
    assert a.method() == f(a) == 1
    assert b.method() == f(b) == 2
    assert c.method() == f(c) == 3


def test_method_incorrect_usage() -> None:
    with pytest.raises(TypeError):
        ClassA.method()  # ty: ignore[missing-argument]
    # rust impl should raise same error type as python
    with pytest.raises(TypeError):
        ClassB.method()  # ty: ignore[missing-argument]


def test_class_method() -> None:
    a = ClassA()
    b = ClassB()
    c = ClassC()

    # test scope resolution works for class methods
    assert a.class_method() == ClassA.class_method() == "A"
    assert b.class_method() == ClassB.class_method() == "B"
    assert c.class_method() == ClassC.class_method() == "C"


def test_static_method() -> None:
    b = ClassB()
    with pytest.raises(AttributeError):
        ClassA.static_method(6)  # ty: ignore[unresolved-attribute]
    assert ClassB.static_method(6) == b.static_method(6) == 1006
