import pytest

# the purpose of this is to test the code paths when a module is already built
from .test_basic import max, passref, throws


def test_passref() -> None:
    # i is immutable
    assert passref(b"abcdef") == 6


def test_throws() -> None:
    with pytest.raises(RuntimeError):
        throws()


def test_max() -> None:
    assert max(1, 3) == 3
