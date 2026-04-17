"""Async Argus adapter with glue-service-specific operations."""

import logging
from datetime import datetime, timezone

from pyargus.async_client import AsyncClient
from pyargus.models import Incident

from zabbixargus.config import ArgusConfig

log = logging.getLogger(__name__)


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

    async def create_incident_from_problem(
        self,
        *,
        description: str,
        source_incident_id: str,
        details_url: str = "",
        level: int,
        tags: list[tuple[str, str]],
        start_time: datetime | None = None,
    ) -> Incident:
        """Create an Argus incident from Zabbix problem data."""
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
        result = await self.client.post_incident(incident)
        log.info(
            "Created Argus incident %s for Zabbix problem %s",
            result.pk,
            source_incident_id,
        )
        return result
