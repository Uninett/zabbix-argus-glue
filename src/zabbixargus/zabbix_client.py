"""Async Zabbix adapter with glue-service-specific operations."""

import logging

from zabbix_utils import AsyncZabbixAPI

from zabbixargus.config import ZabbixConfig

log = logging.getLogger(__name__)


class ZabbixClient:
    """Adapter around AsyncZabbixAPI.

    Use ``self.api`` for direct access to the underlying Zabbix API.
    Composite operations that combine multiple API calls live here.
    """

    def __init__(self, config: ZabbixConfig):
        self._config = config
        self.api: AsyncZabbixAPI | None = None

    async def connect(self):
        self.api = AsyncZabbixAPI(
            url=self._config.url,
            token=self._config.token,
        )
        await self.api.login()
        log.info("Connected to Zabbix at %s", self._config.url)

    async def close(self):
        if self.api:
            await self.api.logout()
            self.api = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def get_problems_with_hosts(self) -> list[dict]:
        """Fetch open problems enriched with host information.

        Zabbix ``problem.get`` does not return host data, so this makes
        a second call to ``event.get`` with ``selectHosts`` and merges
        the results.
        """
        problems = await self.api.problem.get(
            output="extend",
            selectTags="extend",
        )
        if not problems:
            return []

        eventids = [p["eventid"] for p in problems]
        events = await self.api.event.get(
            eventids=eventids,
            selectHosts="extend",
            output=["eventid"],
        )
        hosts_by_eventid = {e["eventid"]: e.get("hosts", []) for e in events}
        for problem in problems:
            problem["hosts"] = hosts_by_eventid.get(problem["eventid"], [])

        return problems
