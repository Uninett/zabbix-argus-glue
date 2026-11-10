"""Tests for the async Zabbix adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from zabbixargus.config import ZabbixConfig
from zabbixargus.zabbix_client import ZabbixClient, primary_hostname


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


class TestGetEventHosts:
    @pytest.mark.asyncio
    async def test_when_event_has_host_then_it_should_return_hosts_and_groups(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        host = {"hostid": "1", "host": "mgmt1", "name": "Management cluster (mgmt1)"}
        mock_api.event.get.return_value = [{"eventid": "100", "hosts": [host]}]
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Web"}, {"name": "Linux servers"}]},
        ]

        hosts, hostgroups = await client.get_event_hosts("100")

        assert hosts == [host]
        assert hostgroups == ["Linux servers", "Web"]
        mock_api.event.get.assert_awaited_once_with(
            eventids=["100"], selectHosts="extend", output=["eventid"]
        )
        mock_api.host.get.assert_awaited_once_with(
            hostids=["1"], selectHostGroups="extend", output=["hostid"]
        )

    @pytest.mark.asyncio
    async def test_when_resolution_disabled_then_it_should_skip_hostgroup_lookup(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
        ]

        hosts, hostgroups = await client.get_event_hosts(
            "100", resolve_hostgroups=False
        )

        assert hosts == [{"hostid": "1", "host": "web01"}]
        assert hostgroups == []
        mock_api.host.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_event_not_found_then_it_should_return_empty(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.event.get.return_value = []

        hosts, hostgroups = await client.get_event_hosts("100")

        assert hosts == []
        assert hostgroups == []
        mock_api.host.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_same_host_within_ttl_then_it_should_use_cache(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.event.get.side_effect = [
            [{"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]}],
            [{"eventid": "200", "hosts": [{"hostid": "1", "host": "web01"}]}],
        ]
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Linux servers"}]},
        ]

        await client.get_event_hosts("100")
        _, hostgroups = await client.get_event_hosts("200")

        assert hostgroups == ["Linux servers"]
        mock_api.host.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_when_cache_entry_expired_then_it_should_refetch(
        self, config, mock_api, monkeypatch
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
        ]
        mock_api.host.get.return_value = [
            {"hostid": "1", "hostgroups": [{"name": "Linux servers"}]},
        ]

        clock = [1000.0]
        monkeypatch.setattr(
            "zabbixargus.zabbix_client.time.monotonic", lambda: clock[0]
        )

        await client.get_event_hosts("100")
        clock[0] += client._HOSTGROUP_CACHE_TTL + 1
        await client.get_event_hosts("100")

        assert mock_api.host.get.await_count == 2

    @pytest.mark.asyncio
    async def test_when_host_has_no_groups_then_it_should_cache_empty(
        self, config, mock_api
    ):
        client = ZabbixClient(config)
        client.api = mock_api
        mock_api.event.get.return_value = [
            {"eventid": "100", "hosts": [{"hostid": "1", "host": "web01"}]},
        ]
        mock_api.host.get.return_value = []

        await client.get_event_hosts("100")
        _, hostgroups = await client.get_event_hosts("100")

        assert hostgroups == []
        mock_api.host.get.assert_awaited_once()


class TestPrimaryHostname:
    def test_when_hosts_present_then_it_should_return_first_technical_name(self):
        hosts = [
            {"hostid": "1", "host": "mgmt1", "name": "Management cluster (mgmt1)"},
            {"hostid": "2", "host": "mgmt2", "name": "mgmt2"},
        ]

        assert primary_hostname(hosts) == "mgmt1"

    def test_when_no_hosts_then_it_should_return_empty(self):
        assert primary_hostname([]) == ""
