"""Tests for the async Argus adapter."""

from unittest.mock import AsyncMock

import pytest
from pyargus.models import Incident

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import ArgusConfig


@pytest.fixture
def config():
    return ArgusConfig(
        url="https://argus.example.com/api/v2",
        token="test-token",
    )


def _make_incident(source_incident_id, pk=1, open_=True):
    return Incident(
        pk=pk,
        source_incident_id=source_incident_id,
        open=open_,
        description="Test",
        level=3,
        tags={},
    )


@pytest.mark.asyncio
async def test_when_incidents_exist_then_get_open_incidents_should_return_keyed_dict(
    config,
):
    client = ArgusClient(config)

    async def fake_get_my_incidents(**kwargs):
        for inc in [_make_incident("100", pk=1), _make_incident("200", pk=2)]:
            yield inc

    client.client.get_my_incidents = fake_get_my_incidents

    result = await client.get_open_incidents()

    assert "100" in result
    assert "200" in result
    assert result["100"].pk == 1
    assert result["200"].pk == 2


@pytest.mark.asyncio
async def test_when_no_incidents_then_get_open_incidents_should_return_empty(config):
    client = ArgusClient(config)

    async def fake_get_my_incidents(**kwargs):
        return
        yield  # make it an async generator

    client.client.get_my_incidents = fake_get_my_incidents

    result = await client.get_open_incidents()

    assert result == {}


@pytest.mark.asyncio
async def test_when_problem_data_given_then_create_incident_should_post_to_argus(
    config,
):
    client = ArgusClient(config)
    client.client.post_incident = AsyncMock(return_value=_make_incident("100", pk=42))

    result = await client.create_incident_from_problem(
        description="High CPU",
        source_incident_id="100",
        level=2,
        tags=[("host", "web01"), ("trigger", "High CPU")],
    )

    assert result.pk == 42
    client.client.post_incident.assert_called_once()
    posted = client.client.post_incident.call_args[0][0]
    assert posted.source_incident_id == "100"
    assert posted.level == 2
    assert posted.tags == {"host": "web01", "trigger": "High CPU"}
