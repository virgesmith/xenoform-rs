from functools import cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class XenoformRsConfig(BaseSettings):
    rustfmt: str = "file"
    disable_ft: str | None = None
    extmodule_root: Path = Path("./ext")
    pyo3_version: str = "0.28"
    verbose: str | None = None

    model_config = SettingsConfigDict(env_prefix="XENOFORM_RS_", extra="ignore")


@cache
def get_config() -> XenoformRsConfig:
    """Cached config"""
    return XenoformRsConfig()
