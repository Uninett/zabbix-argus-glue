"""aiohttp webhook receiver for Zabbix event notifications."""

import asyncio
import ipaddress
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, field_validator

from zabbixargus.argus_client import ArgusClient
from zabbixargus.config import Config, WebhookConfig
from zabbixargus.tags import build_tags
from zabbixargus.zabbix_client import build_details_url

log = logging.getLogger(__name__)

_argus_key = web.AppKey("argus", ArgusClient)
_config_key = web.AppKey("config", Config)


class WebhookPayload(BaseModel):
    """Validated payload from a Zabbix webhook POST.

    Zabbix macro expansion produces strings, but Pydantic coerces
    them into the declared types.  The ``tags`` field is a
    JSON-encoded array from the ``{EVENT.TAGSJSON}`` macro.
    """

    eventid: str
    value: Literal["0", "1"]
    severity: int = 0
    hostname: str = ""
    name: str = ""
    start_time: datetime = Field(datetime.min, alias="clock")
    triggerid: str = ""
    tags: list[dict[str, str]] = []
    update_status: int = 0
    update_action: dict = {}
    update_user: str = ""

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags_json(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v

    @field_validator("update_action", mode="before")
    @classmethod
    def parse_update_action_json(cls, v):
        if isinstance(v, str):
            if not v:
                return {}
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v

    @field_validator("start_time", mode="before")
    @classmethod
    def parse_clock(cls, v):
        if isinstance(v, str) and v:
            try:
                return datetime.strptime(v, "%Y.%m.%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @property
    def event_type(self) -> str:
        """Classify the event as problem, update, or resolve."""
        if self.value == "0":
            return "resolve"
        if self.update_status == 1:
            return "update"
        return "problem"


async def run_webhook_server(argus: ArgusClient, config: Config, stop: asyncio.Event):
    """Run the webhook HTTP server until the stop event is set."""
    app = create_app(argus, config)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.webhook.listen, config.webhook.port)
    await site.start()
    log.info(
        "Webhook server listening on %s:%s",
        config.webhook.listen,
        config.webhook.port,
    )
    try:
        await stop.wait()
    finally:
        await runner.cleanup()


def create_app(argus: ArgusClient, config: Config) -> web.Application:
    """Build the aiohttp application.

    Exposed separately for testing with ``aiohttp.test_utils``.
    """
    app = web.Application()
    app[_argus_key] = argus
    app[_config_key] = config
    app.router.add_post("/webhook", handle_webhook)
    return app


async def handle_webhook(request: web.Request) -> web.Response:
    """Handle an incoming Zabbix webhook POST."""
    config = request.app[_config_key]
    argus = request.app[_argus_key]

    _validate_secret(request, config.webhook)
    _validate_ip(request, config.webhook)

    try:
        raw = await request.json()
    except (json.JSONDecodeError, Exception):
        raise web.HTTPBadRequest(
            text='{"error": "invalid JSON"}', content_type="application/json"
        )

    try:
        payload = WebhookPayload.model_validate(raw)
    except Exception as e:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": str(e)}),
            content_type="application/json",
        )

    match payload.event_type:
        case "problem":
            return await _handle_problem(payload, argus, config)
        case "update":
            return await _handle_update(payload)
        case "resolve":
            return await _handle_resolution(payload, argus)


def _validate_secret(request: web.Request, config: WebhookConfig):
    """Check the shared secret header."""
    if not config.secret:
        return
    provided = request.headers.get("X-Webhook-Secret", "")
    if provided != config.secret:
        raise web.HTTPForbidden(
            text='{"error": "invalid secret"}',
            content_type="application/json",
        )


def _validate_ip(request: web.Request, config: WebhookConfig):
    """Check the source IP against the allowlist."""
    if not config.allowed_ips:
        return
    remote = request.remote
    if remote is None:
        raise web.HTTPForbidden(
            text='{"error": "could not determine remote address"}',
            content_type="application/json",
        )
    remote_addr = ipaddress.ip_address(remote)
    for entry in config.allowed_ips:
        if remote_addr in ipaddress.ip_network(entry, strict=False):
            return
    raise web.HTTPForbidden(
        text='{"error": "source IP not allowed"}',
        content_type="application/json",
    )


async def _handle_problem(
    payload: WebhookPayload, argus: ArgusClient, config: Config
) -> web.Response:
    """Create an Argus incident from a Zabbix problem event."""
    argus_level = config.severity.mapping.get(payload.severity, 5)

    tags = build_tags(
        hostname=payload.hostname,
        trigger=payload.name,
        zabbix_tags=payload.tags,
        config=config.tags,
    )

    details_url = build_details_url(
        eventid=payload.eventid, triggerid=payload.triggerid
    )

    await argus.create_incident_from_problem(
        description=payload.name,
        hostname=payload.hostname,
        prefix_hostname=config.sync.prefix_hostname,
        source_incident_id=payload.eventid,
        details_url=details_url,
        level=argus_level,
        tags=tags,
        start_time=payload.start_time,
    )

    log.info("Webhook: created incident for problem %s", payload.eventid)
    return web.json_response({"status": "created"}, status=201)


async def _handle_update(payload: WebhookPayload) -> web.Response:
    """Log a problem update event.

    Actual Argus event posting will be implemented with ack sync.
    """
    log.info(
        "Webhook: update for problem %s by %s: %s",
        payload.eventid,
        payload.update_user or "unknown",
        payload.update_action,
    )
    return web.json_response({"status": "update_received"})


async def _handle_resolution(
    payload: WebhookPayload, argus: ArgusClient
) -> web.Response:
    """Resolve an Argus incident when a Zabbix problem is resolved."""
    resolved = await argus.resolve_by_source_id(payload.eventid)
    if resolved:
        log.info("Webhook: resolved incident for problem %s", payload.eventid)
        return web.json_response({"status": "resolved"})
    else:
        log.info("Webhook: no open incident found for problem %s", payload.eventid)
        return web.json_response({"status": "not_found"})
