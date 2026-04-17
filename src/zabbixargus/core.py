"""Main orchestrator: runs service components via TaskGroup."""

import asyncio
import logging
import signal

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import Config
from zabbixargus.reconciler import run_reconciliation_loop
from zabbixargus.zabbix_client import ZabbixClient

log = logging.getLogger(__name__)


class _Shutdown(Exception):
    """Raised to trigger TaskGroup cancellation on shutdown."""


async def run(config: Config, *, _stop: asyncio.Event | None = None):
    """Run the glue service until interrupted.

    Uses a TaskGroup so that additional components (webhook receiver,
    ack sync) can be added alongside the reconciliation loop later.

    The optional ``_stop`` parameter is for testing; in production
    SIGINT/SIGTERM set the event automatically.
    """
    stop = _stop or asyncio.Event()
    if _stop is None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

    async with ZabbixClient(config.zabbix) as zabbix:
        argus = ArgusClient(config.argus)
        log.info("Service started")
        try:
            async with asyncio.TaskGroup() as tg:
                if config.reconciliation.enabled:
                    tg.create_task(run_reconciliation_loop(zabbix, argus, config))
                tg.create_task(_wait_for_shutdown(stop))
        except* _Shutdown:
            pass
        log.info("Service stopped")


async def _wait_for_shutdown(stop: asyncio.Event):
    """Wait for the stop event, then trigger TaskGroup cancellation."""
    await stop.wait()
    log.info("Shutdown signal received")
    raise _Shutdown
