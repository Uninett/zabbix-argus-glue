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

    created = await _create_missing(synced, argus_incidents, argus, config)
    closed = await _close_stale(problem_ids, argus_incidents, argus)

    _log_reconciliation_summary(created, closed, config)


def _log_reconciliation_summary(created: int, closed: int, config: Config):
    """Summarize a reconciliation pass.

    When webhooks are enabled, non-zero drift means some events were
    never received as webhooks (glue service was down, webhooks
    misconfigured, or first run); log at WARNING so it is easy to
    spot.  Otherwise log at INFO.  Zero drift is logged at DEBUG.
    """
    if created == 0 and closed == 0:
        log.debug("Reconciliation pass: no drift")
        return
    level = logging.WARNING if config.webhook.enabled else logging.INFO
    log.log(
        level,
        "Reconciliation pass: created %d, closed %d",
        created,
        closed,
    )


async def _create_missing(
    problems: list[dict],
    argus_incidents: dict,
    argus: ArgusClient,
    config: Config,
) -> int:
    created = 0
    for problem in problems:
        eventid = problem["eventid"]
        if eventid in argus_incidents:
            continue

        try:
            await _create_incident_for_problem(problem, argus, config)
            created += 1
        except Exception:
            log.exception("Failed to create incident for problem %s", eventid)
    return created


async def _create_incident_for_problem(
    problem: dict,
    argus: ArgusClient,
    config: Config,
):
    eventid = problem["eventid"]
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
    details_url = _build_details_url(problem)

    await argus.create_incident_from_problem(
        description=problem.get("name", ""),
        hostname=hostname,
        prefix_hostname=config.sync.prefix_hostname,
        source_incident_id=eventid,
        details_url=details_url,
        level=argus_level,
        tags=tags,
        start_time=start_time,
    )


def _build_details_url(problem: dict) -> str:
    """Build a relative URL to the Zabbix problem details page."""
    eventid = problem["eventid"]
    triggerid = problem.get("objectid", "")
    return f"tr_events.php?triggerid={triggerid}&eventid={eventid}"


async def _close_stale(
    open_problem_ids: set[str],
    argus_incidents: dict,
    argus: ArgusClient,
) -> int:
    closed = 0
    for source_id, incident in argus_incidents.items():
        if source_id not in open_problem_ids:
            try:
                await argus.client.resolve_incident(incident)
                log.info(
                    "Closed Argus incident %s (Zabbix problem %s no longer open)",
                    incident.pk,
                    source_id,
                )
                closed += 1
            except Exception:
                log.exception("Failed to close Argus incident %s", incident.pk)
    return closed
