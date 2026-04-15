"""Tests for TOML configuration loading and validation."""

import pytest

from zabbixargus.config import load_config

MINIMAL_TOML = """\
[argus]
url = "https://argus.example.com"
token = "argus-token"

[zabbix]
url = "https://zabbix.example.com"
token = "zabbix-token"
"""

FULL_TOML = """\
[argus]
url = "https://argus.example.com"
token = "argus-token"
timeout = 30

[zabbix]
url = "https://zabbix.example.com"
token = "zabbix-token"

[webhook]
enabled = false
listen = "127.0.0.1"
port = 9090
secret = "my-secret"
allowed_ips = ["10.0.0.0/8"]

[reconciliation]
enabled = false
interval = 120

[sync]
ack_enabled = true
close_enabled = true

[severity]
mapping = {0 = 5, 1 = 5, 2 = 4, 3 = 3, 4 = 2, 5 = 1}
minimum_severity = 2

[tags]
static = ["source=zabbix", "env=prod"]
include_host = false
include_hostgroups = false
include_trigger = false
include_zabbix_tags = false
"""


def test_when_minimal_config_then_load_config_should_use_defaults(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(MINIMAL_TOML)

    config = load_config(config_file)

    assert config.argus.url == "https://argus.example.com"
    assert config.argus.timeout == 10
    assert config.webhook.enabled is True
    assert config.webhook.port == 8080
    assert config.reconciliation.interval == 60
    assert config.sync.ack_enabled is False
    assert config.severity.minimum_severity == 0
    assert config.tags.include_host is True
    assert config.tags.static == []


def test_when_full_config_then_load_config_should_override_defaults(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(FULL_TOML)

    config = load_config(config_file)

    assert config.argus.timeout == 30
    assert config.webhook.enabled is False
    assert config.webhook.listen == "127.0.0.1"
    assert config.webhook.port == 9090
    assert config.webhook.secret == "my-secret"
    assert config.webhook.allowed_ips == ["10.0.0.0/8"]
    assert config.reconciliation.enabled is False
    assert config.reconciliation.interval == 120
    assert config.sync.ack_enabled is True
    assert config.sync.close_enabled is True
    assert config.severity.minimum_severity == 2
    assert config.tags.static == ["source=zabbix", "env=prod"]
    assert config.tags.include_host is False


def test_when_missing_argus_url_then_load_config_should_raise(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[argus]\ntoken = 'x'\n[zabbix]\nurl = 'x'\ntoken = 'x'\n")

    with pytest.raises(Exception):
        load_config(config_file)


def test_when_token_in_env_then_config_should_use_env_var(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[argus]\nurl = 'https://argus'\n[zabbix]\nurl = 'https://zabbix'\n"
    )
    monkeypatch.setenv("ARGUS_TOKEN", "env-argus-token")
    monkeypatch.setenv("ZABBIX_TOKEN", "env-zabbix-token")

    config = load_config(config_file)

    assert config.argus.token == "env-argus-token"
    assert config.zabbix.token == "env-zabbix-token"


def test_when_token_in_file_and_env_then_config_should_prefer_file(
    tmp_path, monkeypatch
):
    config_file = tmp_path / "config.toml"
    config_file.write_text(MINIMAL_TOML)
    monkeypatch.setenv("ARGUS_TOKEN", "env-token")

    config = load_config(config_file)

    assert config.argus.token == "argus-token"
