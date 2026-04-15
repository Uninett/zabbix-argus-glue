"""Tests for the async Zabbix adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zabbixargus.config import ZabbixConfig
from zabbixargus.zabbix_client import ZabbixClient


@pytest.fixture
def config():
    return ZabbixConfig(url="https://zabbix.example.com", token="test-token")


@pytest.fixture
def mock_api():
    api = AsyncMock()
    api.problem = MagicMock()
    api.event = MagicMock()
    api.problem.get = AsyncMock()
    api.event.get = AsyncMock()
    api.login = AsyncMock()
    api.logout = AsyncMock()
    return api


@pytest.mark.asyncio
async def test_when_problems_exist_then_get_problems_with_hosts_should_merge_host_data(
    config, mock_api
):
    client = ZabbixClient(config)
    client.api = mock_api

    mock_api.problem.get.return_value = [
        {"eventid": "100", "severity": "4", "name": "High CPU", "tags": []},
        {"eventid": "200", "severity": "3", "name": "Disk full", "tags": []},
    ]
    mock_api.event.get.return_value = [
        {"eventid": "100", "hosts": [{"host": "web01"}]},
        {"eventid": "200", "hosts": [{"host": "db01"}]},
    ]

    result = await client.get_problems_with_hosts()

    assert len(result) == 2
    assert result[0]["hosts"] == [{"host": "web01"}]
    assert result[1]["hosts"] == [{"host": "db01"}]
    mock_api.event.get.assert_called_once_with(
        eventids=["100", "200"],
        selectHosts="extend",
        output=["eventid"],
    )


@pytest.mark.asyncio
async def test_when_no_problems_then_get_problems_with_hosts_should_return_empty(
    config, mock_api
):
    client = ZabbixClient(config)
    client.api = mock_api
    mock_api.problem.get.return_value = []

    result = await client.get_problems_with_hosts()

    assert result == []
    mock_api.event.get.assert_not_called()


@pytest.mark.asyncio
async def test_when_event_missing_hosts_then_get_problems_with_hosts_should_default_empty(
    config, mock_api
):
    client = ZabbixClient(config)
    client.api = mock_api

    mock_api.problem.get.return_value = [
        {"eventid": "100", "severity": "4", "name": "Test", "tags": []},
    ]
    mock_api.event.get.return_value = [
        {"eventid": "100"},
    ]

    result = await client.get_problems_with_hosts()

    assert result[0]["hosts"] == []
