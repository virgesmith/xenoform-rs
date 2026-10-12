import importlib
import sys
import tempfile
from pathlib import Path

import pytest

_MODULE = '''
from xenoform_rs import rust


@rust(py=False)
def double(x: int) -> int:
    """
    Ok(x * 2)
    """
'''


def test_reimport_after_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # a top-level module, so its sys.modules key is the same as the default rust module name (the file stem)
    (tmp_path / "reimported.py").write_text(_MODULE)
    monkeypatch.syspath_prepend(tmp_path)

    module = importlib.import_module("reimported")
    assert module.double(21) == 42

    # the compiled module is registered under a namespaced key, so it doesn't replace the python module...
    assert sys.modules["reimported"] is module
    assert sys.modules["reimported_ext.reimported"] is not module
    # ...and importing again (e.g. re-running a notebook cell) still finds the python function
    assert importlib.import_module("reimported").double(21) == 42


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        test_reimport_after_call(Path(tmp), pytest.MonkeyPatch())
