import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from xenoform_rs.config import XenoformRsConfig, get_config


def test_config() -> None:

    config = get_config()
    assert config.disable_ft is os.getenv("XENOFORM_RS_DISABLE_FT")
    assert config.extmodule_root == Path(os.getenv("XENOFORM_RS_EXTMODULE_ROOT", "./ext"))
    assert config.pyo3_version == os.getenv("XENOFORM_RS_PYO3_VERSION", "0.29")
    assert config.verbose is os.getenv("XENOFORM_RS_VERBOSE")
    assert config.build_timeout == int(os.getenv("XENOFORM_RS_BUILD_TIMEOUT", "300"))


@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_build_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch, timeout: str) -> None:
    # otherwise every build would time out immediately
    monkeypatch.setenv("XENOFORM_RS_BUILD_TIMEOUT", timeout)
    with pytest.raises(ValidationError, match="build_timeout"):
        XenoformRsConfig()


if __name__ == "__main__":
    test_config()
