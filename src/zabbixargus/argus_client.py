"""Async Argus adapter with glue-service-specific operations."""

import logging
from datetime import datetime, timezone

from pyargus.async_client import AsyncClient
from pyargus.models import Incident
from simple_rest_client.exceptions import ClientError

from zabbixargus.config import ArgusConfig

log = logging.getLogger(__name__)


class DuplicateIncidentError(Exception):
    """Raised when Argus already has an incident for a source_incident_id.

    Argus enforces source_incident_id uniqueness per source across both
    open and closed incidents, so a create can be rejected because an
    incident already exists — commonly one that has since been closed.
    """

    def __init__(self, source_incident_id: str):
        self.source_incident_id = source_incident_id
        super().__init__(
            f"Argus already has an incident for source_incident_id {source_incident_id}"
        )


class ArgusClient:
    """Adapter around pyargus AsyncClient.

    Use ``self.client`` for direct access to the underlying pyargus client.
    Composite operations that combine multiple steps live here.
    """

    def __init__(self, config: ArgusConfig):
        self.client = AsyncClient(
            api_root_url=config.url,
            token=config.token,
            timeout=config.timeout,
        )

    async def get_open_incidents(self) -> dict[str, Incident]:
        """Fetch all open incidents for this source system.

        Returns a dict keyed by ``source_incident_id`` for O(1) lookup.
        """
        incidents = {}
        async for incident in self.client.get_my_incidents(open=True):
            if incident.source_incident_id:
                incidents[incident.source_incident_id] = incident
        return incidents

    async def resolve_incident(self, incident: Incident, description: str = ""):
        """Resolve an Argus incident, recording an optional close reason.

        The description is posted as the text of the closing event, so a
        reader of the Argus event log can see why the incident was
        resolved (e.g. a Zabbix recovery vs. a reconciliation sweep).
        """
        # Pass an explicit tz-aware UTC timestamp; pyargus defaults to a
        # naive datetime.now() which Argus interprets as the server's
        # local timezone, shifting the recorded end_time.
        await self.client.resolve_incident(
            incident,
            timestamp=datetime.now(timezone.utc),
            description=description or None,
        )
        log.info("Resolved Argus incident %s", incident.pk)

    async def resolve_by_source_id(self, source_incident_id: str) -> bool:
        """Resolve an Argus incident by its Zabbix event ID.

        Returns True if the incident was found and resolved, False if
        no matching open incident exists.
        """
        incidents = await self.get_open_incidents()
        incident = incidents.get(source_incident_id)
        if incident is None:
            return False
        await self.resolve_incident(incident, "Resolved in Zabbix")
        return True

    async def create_incident_from_problem(
        self,
        *,
        description: str,
        hostname: str = "",
        prefix_hostname: bool = False,
        source_incident_id: str,
        details_url: str = "",
        level: int,
        tags: list[tuple[str, str]],
        start_time: datetime | None = None,
    ) -> Incident:
        """Create an Argus incident from Zabbix problem data."""
        if prefix_hostname and hostname and hostname not in description:
            description = f"{hostname}: {description}"
        tag_dict = {k: v for k, v in tags}
        incident = Incident(
            description=description,
            source_incident_id=source_incident_id,
            details_url=details_url,
            level=level,
            tags=tag_dict,
            start_time=start_time or datetime.now(timezone.utc),
            end_time=datetime.max,
        )
        try:
            result = await self.client.post_incident(incident)
        except ClientError as e:
            if _is_duplicate_source_id(e):
                raise DuplicateIncidentError(source_incident_id) from e
            raise
        log.info(
            "Created Argus incident %s for Zabbix problem %s",
            result.pk,
            source_incident_id,
        )
        return result

    async def get_incident_by_source_id(
        self, source_incident_id: str
    ) -> Incident | None:
        """Best-effort lookup of an incident (open or closed) by source id.

        Used to enrich logging when a create is rejected as a duplicate.
        Returns ``None`` if it cannot be found or the lookup fails, and
        never raises.  The explicit match guard keeps it correct even if
        Argus ignores the ``source_incident_id`` filter.
        """
        try:
            async for incident in self.client.get_my_incidents(
                source_incident_id=source_incident_id
            ):
                if incident.source_incident_id == source_incident_id:
                    return incident
        except Exception:
            log.debug(
                "Could not look up existing incident for problem %s",
                source_incident_id,
                exc_info=True,
            )
        return None


def _is_duplicate_source_id(error: ClientError) -> bool:
    """Check whether an Argus 400 response indicates a duplicate source ID."""
    response = getattr(error, "response", None)
    if response is None or response.status_code != 400:
        return False
    return "source_incident_id" in str(response.body)


def describe_existing_incident(
    source_incident_id: str, incident: Incident | None
) -> str:
    """Build a log message explaining a skipped duplicate create."""
    if incident is None:
        return (
            f"problem {source_incident_id}: Argus already has an incident "
            f"(could not look it up); not recreating"
        )
    if incident.open:
        return (
            f"problem {source_incident_id}: Argus already has open incident "
            f"{incident.pk}; not recreating"
        )
    return (
        f"problem {source_incident_id}: Argus already has incident {incident.pk}, "
        f"closed at {incident.end_time}; not recreating"
    )
