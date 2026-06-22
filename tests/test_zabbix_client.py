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
    api.host = MagicMock()
    api.problem.get = AsyncMock()
    api.event.get = AsyncMock()
    api.host.get = AsyncMock(return_value=[])
    api.login = AsyncMock()
    api.logout = AsyncMock()
    return api


class TestGetProblemsWithHosts:
    @pytest.mark.asyncio
    async def test_when_problems_exist_then_it_should_merge_host_data(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api

        mock_api.problem.get.return_value = [
            {"eventid": "100", "severity": "4", "name": "High CPU", "tags": []},
            {"eventid": "200", "severity": "3", "name": "Disk full", "tags": []},
        ]
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
            {"eventid": "200", "hosts": [{"hostid": "2", "host": "db01"}]},
        ]

        result = await client.get_problems_with_hosts()

        assert len(result) == 2
        assert result[0]["hosts"] == [{"hostid": "1", "host": "web01"}]
        assert result[1]["hosts"] == [{"hostid": "2", "host": "db01"}]
        mock_api.event.get.assert_called_once_with(
            eventids=["100", "200"],
            selectHosts="extend",
            output=["eventid"],
        )

    @pytest.mark.asyncio
    async def test_when_hosts_have_groups_then_it_should_attach_hostgroups(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api

        mock_api.problem.get.return_value = [
            {"eventid": "100", "severity": "4", "name": "High CPU", "tags": []},
        ]
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
        ]
        mock_api.host.get.return_value = [
            {
                "hostid": "1",
                "hostgroups": [{"name": "Linux servers"}, {"name": "Web"}],
            },
        ]

        result = await client.get_problems_with_hosts()

        assert result[0]["hostgroups"] == ["Linux servers", "Web"]

    @pytest.mark.asyncio
    async def test_when_resolution_disabled_then_it_should_skip_hostgroup_lookup(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api

        mock_api.problem.get.return_value = [
            {"eventid": "100", "severity": "4", "name": "High CPU", "tags": []},
        ]
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
        ]

        result = await client.get_problems_with_hosts(resolve_hostgroups=False)

        assert result[0]["hostgroups"] == []
        mock_api.host.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_no_problems_then_it_should_return_empty(self, config, mock_api):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.problem.get.return_value = []

        result = await client.get_problems_with_hosts()

        assert result == []
        mock_api.event.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_event_missing_hosts_then_it_should_default_empty(
        self, config, mock_api
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
        assert result[0]["hostgroups"] == []


class TestGetHostgroupsForHost:
    @pytest.mark.asyncio
    async def test_when_host_has_groups_then_it_should_return_sorted_names(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Web"}, {"name": "Linux servers"}]},
        ]

        result = await client.get_hostgroups_for_host("web01")

        assert result == ["Linux servers", "Web"]

    @pytest.mark.asyncio
    async def test_when_called_twice_within_ttl_then_it_should_use_cache(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Linux servers"}]},
        ]

        await client.get_hostgroups_for_host("web01")
        await client.get_hostgroups_for_host("web01")

        mock_api.host.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_when_cache_entry_expired_then_it_should_refetch(
        self, config, mock_api, monkeypatch
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Linux servers"}]},
        ]

        clock = [1000.0]
        monkeypatch.setattr(
            "zabbixargus.zabbix_client.time.monotonic", lambda: clock[0]
        )

        await client.get_hostgroups_for_host("web01")
        clock[0] += client._HOSTGROUP_CACHE_TTL + 1
        await client.get_hostgroups_for_host("web01")

        assert mock_api.host.get.await_count == 2
