"""TOML configuration loading and Pydantic v2 validation models."""

import os
import tomllib
from pathlib import Path

import platformdirs
from pydantic import BaseModel, model_validator

DEFAULT_SEVERITY_MAPPING = {0: 5, 1: 5, 2: 4, 3: 3, 4: 2, 5: 1}


class ArgusConfig(BaseModel):
    url: str
    token: str = ""
    timeout: int = 10

    @model_validator(mode="after")
    def token_from_env(self):
        if not self.token:
            self.token = os.environ.get("ARGUS_TOKEN", "")
        return self


class ZabbixConfig(BaseModel):
    url: str
    token: str = ""

    @model_validator(mode="after")
    def token_from_env(self):
        if not self.token:
            self.token = os.environ.get("ZABBIX_TOKEN", "")
        return self


class WebhookConfig(BaseModel):
    enabled: bool = True
    listen: str = "0.0.0.0"
    port: int = 8080
    secret: str = ""
    allowed_ips: list[str] = []


class ReconciliationConfig(BaseModel):
    enabled: bool = True
    interval: int = 60


class SyncConfig(BaseModel):
    ack_enabled: bool = False
    close_enabled: bool = False


class SeverityConfig(BaseModel):
    mapping: dict[int, int] = DEFAULT_SEVERITY_MAPPING
    minimum_severity: int = 0


class TagsConfig(BaseModel):
    static: list[str] = []
    include_host: bool = True
    include_hostgroups: bool = True
    include_trigger: bool = True
    include_zabbix_tags: bool = True


class Config(BaseModel):
    argus: ArgusConfig
    zabbix: ZabbixConfig
    webhook: WebhookConfig = WebhookConfig()
    reconciliation: ReconciliationConfig = ReconciliationConfig()
    sync: SyncConfig = SyncConfig()
    severity: SeverityConfig = SeverityConfig()
    tags: TagsConfig = TagsConfig()


CONFIG_FILENAME = "zabbixargus.toml"
APP_NAME = "zabbixargus"

CONFIG_SEARCH_PATHS = [
    Path(CONFIG_FILENAME),
    Path(platformdirs.user_config_dir(APP_NAME), CONFIG_FILENAME),
    Path(platformdirs.site_config_dir(APP_NAME), CONFIG_FILENAME),
]


def find_config() -> Path | None:
    """Search standard locations for the configuration file."""
    for path in CONFIG_SEARCH_PATHS:
        if path.is_file():
            return path
    return None


def load_config(path: Path) -> Config:
    """Load and validate configuration from a TOML file."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(**data)
