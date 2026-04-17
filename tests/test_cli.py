"""Tests for CLI argument parsing and connectivity verification."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zabbixargus.__main__ import parse_args, verify_zabbix
from zabbixargus.config import ZabbixConfig


def test_when_no_config_then_parser_should_error():
    with pytest.raises(SystemExit):
        parse_args([])


def test_when_config_given_then_parser_should_accept():
    args = parse_args(["--config", "test.toml"])
    assert str(args.config) == "test.toml"
    assert args.verify is False
    assert args.verbose is False


def test_when_verify_flag_then_parser_should_set_it():
    args = parse_args(["--config", "test.toml", "--verify"])
    assert args.verify is True


@pytest.mark.asyncio
async def test_when_zabbix_reachable_then_verify_zabbix_should_return_true():
    config = MagicMock()
    config.zabbix = ZabbixConfig(url="https://zabbix.example.com", token="t")

    mock_client = AsyncMock()
    mock_client.api = MagicMock()
    mock_client.api.version = "7.4.0"

    with patch("zabbixargus.__main__.ZabbixClient", return_value=mock_client):
        result = await verify_zabbix(config)

    assert result is True
    mock_client.connect.assert_called_once()
    mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_when_zabbix_unreachable_then_verify_zabbix_should_return_false():
    config = MagicMock()
    config.zabbix = ZabbixConfig(url="https://zabbix.example.com", token="t")

    mock_client = AsyncMock()
    mock_client.connect.side_effect = ConnectionError("refused")

    with patch("zabbixargus.__main__.ZabbixClient", return_value=mock_client):
        result = await verify_zabbix(config)

    assert result is False
