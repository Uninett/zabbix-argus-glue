"""Tests for the async Argus adapter."""

from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pyargus.models import Incident
from simple_rest_client.exceptions import ClientError

from zabbixargus.argus_client import ArgusClient, DuplicateIncidentError
from zabbixargus.config import ArgusConfig


def _duplicate_error():
    response = MagicMock(
        status_code=400,
        body=[
            "duplicate key value violates unique constraint "
            '"incident_unique_source_incident_id_per_source"\n'
            "DETAIL:  Key (source_incident_id, source_id)=(100, 2) already exists."
        ],
    )
    return ClientError("duplicate", response)


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


class TestCreateIncidentFromProblem:
    @pytest.mark.asyncio
    async def test_when_problem_data_given_then_it_should_post_to_argus(self, config):
        client = ArgusClient(config)
        client.client.post_incident = AsyncMock(
            return_value=_make_incident("100", pk=42)
        )

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

    @pytest.mark.asyncio
    async def test_when_prefix_hostname_enabled_then_it_should_include_host(
        self, config
    ):
        client = ArgusClient(config)
        client.client.post_incident = AsyncMock(
            return_value=_make_incident("100", pk=1)
        )

        await client.create_incident_from_problem(
            description="High CPU",
            hostname="web01",
            prefix_hostname=True,
            source_incident_id="100",
            level=2,
            tags=[],
        )

        posted = client.client.post_incident.call_args[0][0]
        assert posted.description == "web01: High CPU"

    @pytest.mark.asyncio
    async def test_when_hostname_already_in_description_then_it_should_not_prefix(
        self, config
    ):
        client = ArgusClient(config)
        client.client.post_incident = AsyncMock(
            return_value=_make_incident("100", pk=1)
        )

        await client.create_incident_from_problem(
            description="web01: High CPU",
            hostname="web01",
            prefix_hostname=True,
            source_incident_id="100",
            level=2,
            tags=[],
        )

        posted = client.client.post_incident.call_args[0][0]
        assert posted.description == "web01: High CPU"

    @pytest.mark.asyncio
    async def test_when_prefix_hostname_disabled_then_it_should_be_unchanged(
        self, config
    ):
        client = ArgusClient(config)
        client.client.post_incident = AsyncMock(
            return_value=_make_incident("100", pk=1)
        )

        await client.create_incident_from_problem(
            description="High CPU",
            hostname="web01",
            prefix_hostname=False,
            source_incident_id="100",
            level=2,
            tags=[],
        )

        posted = client.client.post_incident.call_args[0][0]
        assert posted.description == "High CPU"

    @pytest.mark.asyncio
    async def test_when_argus_reports_duplicate_then_it_should_raise_duplicate_error(
        self, config
    ):
        client = ArgusClient(config)
        client.client.post_incident = AsyncMock(side_effect=_duplicate_error())

        with pytest.raises(DuplicateIncidentError):
            await client.create_incident_from_problem(
                description="High CPU", source_incident_id="100", level=2, tags=[]
            )

    @pytest.mark.asyncio
    async def test_when_argus_errors_for_other_reason_then_it_should_reraise(
        self, config
    ):
        client = ArgusClient(config)
        response = MagicMock(status_code=400, body=["some other validation error"])
        client.client.post_incident = AsyncMock(
            side_effect=ClientError("other", response)
        )

        with pytest.raises(ClientError):
            await client.create_incident_from_problem(
                description="High CPU", source_incident_id="100", level=2, tags=[]
            )


class TestGetIncidentBySourceId:
    @pytest.mark.asyncio
    async def test_when_incident_matches_then_it_should_return_it(self, config):
        client = ArgusClient(config)

        async def fake_get_my_incidents(**kwargs):
            yield _make_incident("100", pk=7, open_=False)

        client.client.get_my_incidents = fake_get_my_incidents

        result = await client.get_incident_by_source_id("100")

        assert result.pk == 7

    @pytest.mark.asyncio
    async def test_when_filter_ignored_then_it_should_only_return_a_match(self, config):
        client = ArgusClient(config)

        async def fake_get_my_incidents(**kwargs):
            # Simulate Argus ignoring the source_incident_id filter.
            yield _make_incident("999", pk=7)

        client.client.get_my_incidents = fake_get_my_incidents

        result = await client.get_incident_by_source_id("100")

        assert result is None

    @pytest.mark.asyncio
    async def test_when_lookup_fails_then_it_should_return_none(self, config):
        client = ArgusClient(config)

        async def fake_get_my_incidents(**kwargs):
            raise RuntimeError("boom")
            yield  # make it an async generator

        client.client.get_my_incidents = fake_get_my_incidents

        result = await client.get_incident_by_source_id("100")

        assert result is None


class TestResolveIncident:
    @pytest.mark.asyncio
    async def test_when_reason_given_then_it_should_post_it_as_description(
        self, config
    ):
        client = ArgusClient(config)
        client.client.resolve_incident = AsyncMock()

        await client.resolve_incident(_make_incident("100"), "Resolved in Zabbix")

        client.client.resolve_incident.assert_awaited_once()
        kwargs = client.client.resolve_incident.call_args.kwargs
        assert kwargs["description"] == "Resolved in Zabbix"

    @pytest.mark.asyncio
    async def test_when_no_reason_given_then_it_should_not_post_a_description(
        self, config
    ):
        client = ArgusClient(config)
        client.client.resolve_incident = AsyncMock()

        await client.resolve_incident(_make_incident("100"))

        kwargs = client.client.resolve_incident.call_args.kwargs
        assert kwargs["description"] is None

    @pytest.mark.asyncio
    async def test_when_resolving_then_it_should_use_tz_aware_utc_timestamp(
        self, config
    ):
        client = ArgusClient(config)
        client.client.resolve_incident = AsyncMock()

        await client.resolve_incident(_make_incident("100"))

        timestamp = client.client.resolve_incident.call_args.kwargs["timestamp"]
        assert timestamp.tzinfo == timezone.utc


class TestResolveBySourceId:
    @pytest.mark.asyncio
    async def test_when_source_id_matches_then_it_should_resolve_in_zabbix(
        self, config
    ):
        client = ArgusClient(config)
        client.get_open_incidents = AsyncMock(
            return_value={"100": _make_incident("100")}
        )
        client.client.resolve_incident = AsyncMock()

        result = await client.resolve_by_source_id("100")

        assert result is True
        kwargs = client.client.resolve_incident.call_args.kwargs
        assert kwargs["description"] == "Resolved in Zabbix"

    @pytest.mark.asyncio
    async def test_when_source_id_unknown_then_it_should_return_false(self, config):
        client = ArgusClient(config)
        client.get_open_incidents = AsyncMock(return_value={})
        client.client.resolve_incident = AsyncMock()

        result = await client.resolve_by_source_id("999")

        assert result is False
        client.client.resolve_incident.assert_not_awaited()
