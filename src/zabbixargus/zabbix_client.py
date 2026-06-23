"""Async Zabbix adapter with glue-service-specific operations."""

import logging
import time

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

    _HOSTGROUP_CACHE_TTL = 300  # seconds

    def __init__(self, config: ZabbixConfig):
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self.api: AsyncZabbixAPI | None = None
        self._hostgroup_cache: dict[str, tuple[float, list[str]]] = {}

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

    async def get_problems_with_hosts(
        self, *, resolve_hostgroups: bool = True
    ) -> list[dict]:
        """Fetch open problems enriched with host and host-group data.

        Zabbix ``problem.get`` does not return host data, so this makes
        a second call to ``event.get`` with ``selectHosts`` to find the
        hosts, then (when ``resolve_hostgroups`` is set) a ``host.get``
        to resolve their host groups, and merges everything back onto
        each problem.  Each problem gains a ``hosts`` list and a sorted,
        de-duplicated ``hostgroups`` list (empty when resolution is off).
        """
        problems = await self.api.problem.get(
            output="extend",
            selectTags="extend",
        )
        if not problems:
            return []

        hosts_by_eventid = await self._get_hosts_by_eventid(
            [problem["eventid"] for problem in problems]
        )
        groups_by_hostid = {}
        if resolve_hostgroups:
            all_hostids = {
                host["hostid"] for hosts in hosts_by_eventid.values() for host in hosts
            }
            groups_by_hostid = await self._get_hostgroups_by_hostid(all_hostids)

        for problem in problems:
            hosts = hosts_by_eventid.get(problem["eventid"], [])
            problem["hosts"] = hosts
            problem["hostgroups"] = _hostgroup_names(hosts, groups_by_hostid)

        return problems

    async def get_hostgroups_for_host(self, hostname: str) -> list[str]:
        """Return the host groups a host belongs to, with a TTL cache.

        Webhook events arrive one host at a time and host-group
        membership changes rarely, so results are cached for
        ``_HOSTGROUP_CACHE_TTL`` seconds to avoid an API call per event.
        The cache keeps one entry per hostname seen; its size is bounded
        by the Zabbix host inventory and entries are never evicted (only
        refreshed in place), which is fine for that cardinality.
        """
        now = time.monotonic()
        cached = self._hostgroup_cache.get(hostname)
        if cached is not None and now - cached[0] < self._HOSTGROUP_CACHE_TTL:
            return cached[1]

        groups = await self._fetch_hostgroups_for_host(hostname)
        self._hostgroup_cache[hostname] = (now, groups)
        return groups

    async def _get_hosts_by_eventid(self, eventids: list[str]) -> dict[str, list[dict]]:
        """Map each event id to its hosts.

        ``problem.get`` omits host data, so this uses ``event.get`` with
        ``selectHosts``.  ``selectHosts="extend"`` must include each
        host's ``hostid``; host-group resolution relies on it.
        """
        events = await self.api.event.get(
            eventids=eventids,
            selectHosts="extend",
            output=["eventid"],
        )
        return {event["eventid"]: event.get("hosts", []) for event in events}

    async def _get_hostgroups_by_hostid(
        self, hostids: set[str]
    ) -> dict[str, list[str]]:
        """Map each host id to the names of the host groups it belongs to."""
        if not hostids:
            return {}
        hosts = await self.api.host.get(
            hostids=list(hostids),
            selectHostGroups="extend",
            output=["hostid"],
        )
        return {
            host["hostid"]: [group["name"] for group in host.get("hostgroups", [])]
            for host in hosts
        }

    async def _fetch_hostgroups_for_host(self, hostname: str) -> list[str]:
        """Look up a single host's groups by name (uncached)."""
        hosts = await self.api.host.get(
            filter={"host": [hostname]},
            selectHostGroups="extend",
            output=["hostid"],
        )
        groups = {
            group["name"] for host in hosts for group in host.get("hostgroups", [])
        }
        return sorted(groups)


def _hostgroup_names(
    hosts: list[dict], groups_by_hostid: dict[str, list[str]]
) -> list[str]:
    """Sorted, de-duplicated host-group names across a problem's hosts."""
    names = {
        name for host in hosts for name in groups_by_hostid.get(host["hostid"], [])
    }
    return sorted(names)


def build_details_url(*, eventid: str, triggerid: str) -> str:
    """Build a relative URL to the Zabbix problem details page."""
    return f"tr_events.php?triggerid={triggerid}&eventid={eventid}"
