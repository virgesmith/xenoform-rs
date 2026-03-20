from abc import abstractmethod


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
