"""Integration tests for reconciliation against a live Argus server."""

from unittest.mock import AsyncMock

import pytest

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import (
    ArgusConfig,
    Config,
    TagsConfig,
    ZabbixConfig,
)
from zabbixargus.reconciler import reconcile

pytestmark = pytest.mark.integration


def _problem(eventid, severity="4", name="Test problem", hostname="web01"):
    return {
        "eventid": eventid,
        "severity": severity,
        "name": name,
        "clock": "1700000000",
        "tags": [],
        "hosts": [{"host": hostname}],
    }


def _config():
    return Config(
        argus=ArgusConfig(url="https://unused", token="unused"),
        zabbix=ZabbixConfig(url="https://unused", token="unused"),
        tags=TagsConfig(static=["source=zabbix"]),
    )


@pytest.fixture
def argus(argus_api_url, argus_source_system_token):
    config = ArgusConfig(url=argus_api_url, token=argus_source_system_token)
    return ArgusClient(config)


@pytest.fixture
def zabbix():
    return AsyncMock()


@pytest.mark.asyncio
async def test_when_zabbix_has_problems_then_reconcile_should_create_argus_incidents(
    argus, zabbix
):
    zabbix.get_problems_with_hosts.return_value = [
        _problem("reconcile-100"),
        _problem("reconcile-200", severity="5", name="Disk full", hostname="db01"),
    ]

    await reconcile(zabbix, argus, _config())

    incidents = await argus.get_open_incidents()
    assert "reconcile-100" in incidents
    assert "reconcile-200" in incidents


@pytest.mark.asyncio
async def test_when_problem_resolved_then_reconcile_should_close_argus_incident(
    argus, zabbix
):
    # First reconcile creates the incident
    zabbix.get_problems_with_hosts.return_value = [_problem("reconcile-300")]
    await reconcile(zabbix, argus, _config())

    incidents = await argus.get_open_incidents()
    assert "reconcile-300" in incidents

    # Problem disappears from Zabbix, second reconcile should close it
    zabbix.get_problems_with_hosts.return_value = []
    await reconcile(zabbix, argus, _config())

    incidents = await argus.get_open_incidents()
    assert "reconcile-300" not in incidents
