from abc import abstractmethod
from typing import Annotated

# imported by test_constants: the annotation stays here, only the value travels with the import
BIG: Annotated[int, "u64"] = 2**40


class Base:
    @abstractmethod
    def method(self) -> int: ...


class ClassA(Base):
    X: str = "A"

    def __init__(self) -> None:
        self.i = 1

    def method(self) -> int:
        return self.i

    @classmethod
    def class_method(cls) -> str:
        return cls.X
