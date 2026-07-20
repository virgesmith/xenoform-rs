import logging
import types
from collections.abc import Iterator

import pytest

from xenoform_rs import compile as compile_mod
from xenoform_rs.compile import _configure_verbose_logging, logger, rust


@pytest.fixture(autouse=True)
def _restore_logger() -> Iterator[None]:
    """Snapshot and restore the library logger's state around each test."""
    saved = (logger.level, list(logger.handlers), logger.propagate)
    yield
    logger.setLevel(saved[0])
    logger.handlers = saved[1]
    logger.propagate = saved[2]


def test_configure_verbose_logging_isolates_from_root() -> None:
    logger.handlers = []
    root_handlers_before = list(logging.getLogger().handlers)

    _configure_verbose_logging()

    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    # never touches the root logger / basicConfig
    assert logger.propagate is False
    assert logging.getLogger().handlers == root_handlers_before

    # idempotent: a second call must not stack duplicate handlers
    _configure_verbose_logging()
    assert len(logger.handlers) == 1


def test_rust_decorator_enables_verbose_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    logger.handlers = []
    monkeypatch.setattr(compile_mod, "get_config", lambda: types.SimpleNamespace(verbose=""))

    rust(py=False)  # invoking the factory triggers the config check

    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1


if __name__ == "__main__":
    test_configure_verbose_logging_isolates_from_root()
    test_rust_decorator_enables_verbose_from_config(pytest.MonkeyPatch())
