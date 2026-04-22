"""Tests for the service orchestrator."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from zabbixargus.config import (
    ArgusConfig,
    Config,
    ReconciliationConfig,
    TagsConfig,
    WebhookConfig,
    ZabbixConfig,
)
from zabbixargus.core import run


def _config(**overrides):
    defaults = dict(
        argus=ArgusConfig(url="https://argus", token="t"),
        zabbix=ZabbixConfig(url="https://zabbix", token="t"),
        tags=TagsConfig(static=["source=zabbix"]),
        reconciliation=ReconciliationConfig(enabled=True, interval=1),
    )
    defaults.update(overrides)
    return Config(**defaults)


@pytest.mark.asyncio
async def test_when_started_then_run_should_call_reconcile_before_shutdown():
    config = _config()
    stop = asyncio.Event()
    reconcile_called = asyncio.Event()

    async def fake_reconciliation_loop(zabbix, argus, cfg):
        reconcile_called.set()
        await asyncio.sleep(3600)

    with (
        patch("zabbixargus.core.ZabbixClient") as mock_zabbix_cls,
        patch("zabbixargus.core.ArgusClient"),
        patch(
            "zabbixargus.core.run_reconciliation_loop",
            side_effect=fake_reconciliation_loop,
        ),
    ):
        mock_zabbix = AsyncMock()
        mock_zabbix_cls.return_value = mock_zabbix
        mock_zabbix.__aenter__ = AsyncMock(return_value=mock_zabbix)
        mock_zabbix.__aexit__ = AsyncMock(return_value=False)

        async def stop_after_reconcile():
            await reconcile_called.wait()
            stop.set()

        stopper = asyncio.create_task(stop_after_reconcile())
        await run(config, _stop=stop)
        await stopper

    assert reconcile_called.is_set()


@pytest.mark.asyncio
async def test_when_reconciliation_disabled_then_run_should_not_start_loop():
    config = _config(reconciliation=ReconciliationConfig(enabled=False, interval=60))
    stop = asyncio.Event()

    with (
        patch("zabbixargus.core.ZabbixClient") as mock_zabbix_cls,
        patch("zabbixargus.core.ArgusClient"),
        patch("zabbixargus.core.run_reconciliation_loop") as mock_loop,
    ):
        mock_zabbix = AsyncMock()
        mock_zabbix_cls.return_value = mock_zabbix
        mock_zabbix.__aenter__ = AsyncMock(return_value=mock_zabbix)
        mock_zabbix.__aexit__ = AsyncMock(return_value=False)

        async def stop_quickly():
            await asyncio.sleep(0.05)
            stop.set()

        stopper = asyncio.create_task(stop_quickly())
        await run(config, _stop=stop)
        await stopper

    mock_loop.assert_not_called()


@pytest.mark.asyncio
async def test_when_webhook_enabled_then_run_should_start_server():
    config = _config(webhook=WebhookConfig(enabled=True))
    stop = asyncio.Event()

    with (
        patch("zabbixargus.core.ZabbixClient") as mock_zabbix_cls,
        patch("zabbixargus.core.ArgusClient"),
        patch("zabbixargus.core.run_reconciliation_loop", new_callable=AsyncMock),
        patch("zabbixargus.core.run_webhook_server") as mock_webhook,
    ):
        mock_zabbix = AsyncMock()
        mock_zabbix_cls.return_value = mock_zabbix
        mock_zabbix.__aenter__ = AsyncMock(return_value=mock_zabbix)
        mock_zabbix.__aexit__ = AsyncMock(return_value=False)

        webhook_called = asyncio.Event()

        async def fake_webhook_server(argus, cfg, stop_event):
            webhook_called.set()
            await asyncio.sleep(3600)

        mock_webhook.side_effect = fake_webhook_server

        async def stop_after_webhook():
            await webhook_called.wait()
            stop.set()

        stopper = asyncio.create_task(stop_after_webhook())
        await run(config, _stop=stop)
        await stopper

    assert webhook_called.is_set()


@pytest.mark.asyncio
async def test_when_webhook_disabled_then_run_should_not_start_server():
    config = _config(webhook=WebhookConfig(enabled=False))
    stop = asyncio.Event()

    with (
        patch("zabbixargus.core.ZabbixClient") as mock_zabbix_cls,
        patch("zabbixargus.core.ArgusClient"),
        patch("zabbixargus.core.run_reconciliation_loop", new_callable=AsyncMock),
        patch("zabbixargus.core.run_webhook_server") as mock_webhook,
    ):
        mock_zabbix = AsyncMock()
        mock_zabbix_cls.return_value = mock_zabbix
        mock_zabbix.__aenter__ = AsyncMock(return_value=mock_zabbix)
        mock_zabbix.__aexit__ = AsyncMock(return_value=False)

        async def stop_quickly():
            await asyncio.sleep(0.05)
            stop.set()

        stopper = asyncio.create_task(stop_quickly())
        await run(config, _stop=stop)
        await stopper

    mock_webhook.assert_not_called()
