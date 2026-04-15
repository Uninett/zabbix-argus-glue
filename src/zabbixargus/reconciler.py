"""Full sync and drift detection between Zabbix and Argus."""

import asyncio
import logging
from datetime import datetime, timezone

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import Config
from zabbixargus.tags import build_tags
from zabbixargus.zabbix_client import ZabbixClient

log = logging.getLogger(__name__)


async def run_reconciliation_loop(
    zabbix: ZabbixClient, argus: ArgusClient, config: Config
):
    """Run reconciliation on startup and then at a regular interval."""
    while True:
        try:
            await reconcile(zabbix, argus, config)
        except Exception:
            log.exception("Reconciliation failed")
        await asyncio.sleep(config.reconciliation.interval)


async def reconcile(zabbix: ZabbixClient, argus: ArgusClient, config: Config):
    """Run a single reconciliation pass.

    Fetches open problems from Zabbix and open incidents from Argus,
    then creates missing incidents and closes stale ones.
    """
    problems = await zabbix.get_problems_with_hosts()
    argus_incidents = await argus.get_open_incidents()

    minimum = config.severity.minimum_severity
    synced = [p for p in problems if int(p["severity"]) >= minimum]
    problem_ids = {p["eventid"] for p in synced}

    await _create_missing(synced, argus_incidents, argus, config)
    await _close_stale(problem_ids, argus_incidents, argus)


async def _create_missing(
    problems: list[dict],
    argus_incidents: dict,
    argus: ArgusClient,
    config: Config,
):
    for problem in problems:
        eventid = problem["eventid"]
        if eventid in argus_incidents:
            continue

        hosts = problem.get("hosts", [])
        hostname = hosts[0]["host"] if hosts else ""
        hostgroups = []  # TODO: enrich when hostgroup data is available

        zabbix_severity = int(problem["severity"])
        argus_level = config.severity.mapping[zabbix_severity]

        tags = build_tags(
            hostname=hostname,
            hostgroups=hostgroups,
            trigger=problem.get("name", ""),
            zabbix_tags=problem.get("tags", []),
            config=config.tags,
        )

        start_time = datetime.fromtimestamp(int(problem["clock"]), tz=timezone.utc)

        await argus.create_incident_from_problem(
            description=problem.get("name", ""),
            source_incident_id=eventid,
            level=argus_level,
            tags=tags,
            start_time=start_time,
        )


async def _close_stale(
    open_problem_ids: set[str],
    argus_incidents: dict,
    argus: ArgusClient,
):
    for source_id, incident in argus_incidents.items():
        if source_id not in open_problem_ids:
            await argus.client.resolve_incident(incident)
            log.info(
                "Closed Argus incident %s (Zabbix problem %s no longer open)",
                incident.pk,
                source_id,
            )
