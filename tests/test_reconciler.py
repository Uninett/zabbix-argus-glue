"""Tests for reconciliation logic."""

from unittest.mock import AsyncMock

import pytest
from pyargus.models import Incident

from zabbixargus.config import (
    ArgusConfig,
    Config,
    SeverityConfig,
    TagsConfig,
    WebhookConfig,
    ZabbixConfig,
)
from zabbixargus.reconciler import reconcile


def _config(webhook_enabled=True, **severity_overrides):
    return Config(
        argus=ArgusConfig(url="https://argus", token="t"),
        zabbix=ZabbixConfig(url="https://zabbix", token="t"),
        webhook=WebhookConfig(enabled=webhook_enabled),
        severity=SeverityConfig(**severity_overrides),
        tags=TagsConfig(static=["source=zabbix"]),
    )


def _problem(eventid, severity="4", name="Test", hostname="web01"):
    return {
        "eventid": eventid,
        "severity": severity,
        "name": name,
        "clock": "1700000000",
        "tags": [],
        "hosts": [{"host": hostname}],
    }


def _incident(source_incident_id, pk=1):
    return Incident(
        pk=pk,
        source_incident_id=source_incident_id,
        open=True,
        description="Test",
        level=3,
        tags={},
    )


@pytest.fixture
def zabbix():
    client = AsyncMock()
    client.get_problems_with_hosts = AsyncMock(return_value=[])
    return client


@pytest.fixture
def argus():
    client = AsyncMock()
    client.get_open_incidents = AsyncMock(return_value={})
    client.create_incident_from_problem = AsyncMock()
    client.client = AsyncMock()
    client.client.resolve_incident = AsyncMock()
    return client


class TestReconcile:
    @pytest.mark.asyncio
    async def test_when_zabbix_has_new_problem_then_it_should_create_incident(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100")]
        argus.get_open_incidents.return_value = {}

        await reconcile(zabbix, argus, _config())

        argus.create_incident_from_problem.assert_called_once()
        call_kwargs = argus.create_incident_from_problem.call_args.kwargs
        assert call_kwargs["source_incident_id"] == "100"

    @pytest.mark.asyncio
    async def test_when_problem_already_in_argus_then_it_should_skip_it(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100")]
        argus.get_open_incidents.return_value = {"100": _incident("100")}

        await reconcile(zabbix, argus, _config())

        argus.create_incident_from_problem.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_argus_incident_has_no_matching_problem_then_it_should_close_it(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = []
        argus.get_open_incidents.return_value = {"100": _incident("100")}

        await reconcile(zabbix, argus, _config())

        argus.client.resolve_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_when_problem_below_threshold_then_it_should_skip_it(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100", severity="1")]
        argus.get_open_incidents.return_value = {}

        await reconcile(zabbix, argus, _config(minimum_severity=3))

        argus.create_incident_from_problem.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_severity_mapped_then_it_should_use_argus_level(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100", severity="5")]
        argus.get_open_incidents.return_value = {}

        await reconcile(zabbix, argus, _config())

        call_kwargs = argus.create_incident_from_problem.call_args.kwargs
        assert call_kwargs["level"] == 1  # Zabbix 5 (Disaster) → Argus 1 (Critical)

    @pytest.mark.asyncio
    async def test_when_one_problem_fails_then_it_should_continue_with_others(
        self, zabbix, argus
    ):
        zabbix.get_problems_with_hosts.return_value = [
            _problem("100"),
            _problem("200"),
        ]
        argus.get_open_incidents.return_value = {}
        argus.create_incident_from_problem.side_effect = [
            Exception("API error"),
            _incident("200"),
        ]

        await reconcile(zabbix, argus, _config())

        assert argus.create_incident_from_problem.call_count == 2


class TestReconciliationSummary:
    @pytest.mark.asyncio
    async def test_when_drift_and_webhooks_enabled_then_it_should_log_warning(
        self, zabbix, argus, caplog
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100")]
        argus.get_open_incidents.return_value = {}

        with caplog.at_level("WARNING", logger="zabbixargus.reconciler"):
            await reconcile(zabbix, argus, _config(webhook_enabled=True))

        assert any(
            "Reconciliation pass: created 1, closed 0" in r.message
            and r.levelname == "WARNING"
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_when_drift_and_webhooks_disabled_then_it_should_log_info(
        self, zabbix, argus, caplog
    ):
        zabbix.get_problems_with_hosts.return_value = [_problem("100")]
        argus.get_open_incidents.return_value = {}

        with caplog.at_level("INFO", logger="zabbixargus.reconciler"):
            await reconcile(zabbix, argus, _config(webhook_enabled=False))

        summary = [r for r in caplog.records if "Reconciliation pass" in r.message]
        assert len(summary) == 1
        assert summary[0].levelname == "INFO"

    @pytest.mark.asyncio
    async def test_when_no_drift_then_it_should_not_log_summary_above_debug(
        self, zabbix, argus, caplog
    ):
        zabbix.get_problems_with_hosts.return_value = []
        argus.get_open_incidents.return_value = {}

        with caplog.at_level("INFO", logger="zabbixargus.reconciler"):
            await reconcile(zabbix, argus, _config())

        assert not any("Reconciliation pass" in r.message for r in caplog.records)
