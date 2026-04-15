"""Integration tests for the Argus client adapter against a live Argus server."""

import pytest

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import ArgusConfig

pytestmark = pytest.mark.integration


@pytest.fixture
def argus(argus_api_url, argus_source_system_token):
    config = ArgusConfig(url=argus_api_url, token=argus_source_system_token)
    return ArgusClient(config)


@pytest.mark.asyncio
async def test_when_incident_created_then_get_open_incidents_should_return_it(argus):
    result = await argus.create_incident_from_problem(
        description="Integration test incident",
        source_incident_id="integration-100",
        level=3,
        tags=[("host", "test01"), ("source", "zabbix")],
    )

    assert result.pk is not None
    assert result.source_incident_id == "integration-100"

    incidents = await argus.get_open_incidents()
    assert "integration-100" in incidents


@pytest.mark.asyncio
async def test_when_incident_resolved_then_get_open_incidents_should_not_return_it(
    argus,
):
    created = await argus.create_incident_from_problem(
        description="Will be resolved",
        source_incident_id="integration-200",
        level=2,
        tags=[("host", "test02")],
    )

    await argus.client.resolve_incident(created)

    incidents = await argus.get_open_incidents()
    assert "integration-200" not in incidents
