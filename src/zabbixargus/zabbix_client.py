"""Async Zabbix adapter with glue-service-specific operations."""

import logging

import aiohttp
from zabbix_utils import AsyncZabbixAPI

from zabbixargus.config import ZabbixConfig

log = logging.getLogger(__name__)


class ZabbixClient:
    """Adapter around AsyncZabbixAPI using token-based auth.

    Use ``self.api`` for direct access to the underlying Zabbix API.
    Composite operations that combine multiple API calls live here.

    Zabbix API tokens are stateless (no server-side session), so there
    is no login/logout cycle.  The ``zabbix-utils`` library still
    requires ``login()`` to register the token internally, but no API
    call is made.
    """

    def __init__(self, config: ZabbixConfig):
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self.api: AsyncZabbixAPI | None = None

    async def connect(self):
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=True),
        )
        self.api = AsyncZabbixAPI(
            url=self._config.url,
            token=self._config.token,
            client_session=self._session,
        )
        # Registers the token internally; no API call is made.
        await self.api.login()
        log.info(
            "Connected to Zabbix at %s (version %s)", self._config.url, self.api.version
        )

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
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
