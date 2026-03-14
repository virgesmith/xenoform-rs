from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class XenoformConfig(BaseSettings):
    rustfmt: str = "file"
    disable_ft: str | None = None
    extmodule_root: Path = Path("./ext")
    pyo3_version: str = "0.28"

    model_config = SettingsConfigDict(env_prefix="XENOFORM_RS_", extra="ignore")


@cache
def get_config() -> XenoformConfig:
    """Cached config"""
    return XenoformConfig()
