import os
from pathlib import Path

from xenoform_rs.config import get_config


def test_config() -> None:

    config = get_config()
    assert config.disable_ft is os.getenv("XENOFORM_RS_DISABLE_FT")
    assert config.extmodule_root == Path(os.getenv("XENOFORM_RS_EXTMODULE_ROOT", "./ext"))
    assert config.pyo3_version == os.getenv("XENOFORM_RS_DISABLE_FT", "0.28")


if __name__ == "__main__":
    test_config()
