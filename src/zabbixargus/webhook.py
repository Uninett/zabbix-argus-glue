"""aiohttp webhook receiver for Zabbix event notifications."""

import asyncio
import ipaddress
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from aiohttp import web
from pydantic import BaseModel, ConfigDict, Field, field_validator

from zabbixargus.argus_client import (
    ArgusClient,
    DuplicateIncidentError,
    describe_existing_incident,
)
from zabbixargus.config import Config, WebhookConfig
from zabbixargus.tags import build_tags
from zabbixargus.zabbix_client import ZabbixClient, build_details_url

log = logging.getLogger(__name__)

_argus_key = web.AppKey("argus", ArgusClient)
_zabbix_key = web.AppKey("zabbix", ZabbixClient)
_config_key = web.AppKey("config", Config)


class WebhookPayload(BaseModel):
    """Validated payload from a Zabbix webhook POST.

    Zabbix macro expansion produces strings, but Pydantic coerces
    them into the declared types.  The ``tags`` field is a
    JSON-encoded array from the ``{EVENT.TAGSJSON}`` macro.  The
    ``timestamp`` field is a Unix epoch from ``{EVENT.TIMESTAMP}``
    (Zabbix 7.2+).
    """

    eventid: str
    value: Literal["0", "1"]
    severity: int = 0
    hostname: str = ""
    name: str = ""
    start_time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        alias="timestamp",
    )
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
    def parse_timestamp(cls, v):
        if v in (None, ""):
            return datetime.now(timezone.utc)
        try:
            return datetime.fromtimestamp(int(v), tz=timezone.utc)
        except (ValueError, OSError, TypeError):
            log.warning("Webhook: unparseable timestamp %r, using current time", v)
            return datetime.now(timezone.utc)

    @property
    def event_type(self) -> str:
        """Classify the event as problem, update, or resolve."""
        if self.value == "0":
            return "resolve"
        if self.update_status == 1:
            return "update"
        return "problem"


async def run_webhook_server(
    argus: ArgusClient, zabbix: ZabbixClient, config: Config, stop: asyncio.Event
):
    """Run the webhook HTTP server until the stop event is set."""
    app = create_app(argus, zabbix, config)
    runner = web.AppRunner(
        app, access_log_format=_access_log_format(config.webhook.real_ip_header)
    )
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


def create_app(
    argus: ArgusClient, zabbix: ZabbixClient, config: Config
) -> web.Application:
    """Build the aiohttp application.

    Exposed separately for testing with ``aiohttp.test_utils``.
    """
    app = web.Application()
    app[_argus_key] = argus
    app[_zabbix_key] = zabbix
    app[_config_key] = config
    app.router.add_post("/webhook", handle_webhook)
    return app


async def handle_webhook(request: web.Request) -> web.Response:
    """Handle an incoming Zabbix webhook POST."""
    config = request.app[_config_key]
    argus = request.app[_argus_key]
    zabbix = request.app[_zabbix_key]

    _validate_secret(request, config.webhook)
    _validate_ip(request, config.webhook)

    try:
        raw = await request.json()
    except json.JSONDecodeError:
        raise _error_response(web.HTTPBadRequest, "invalid JSON")

    try:
        payload = WebhookPayload.model_validate(raw)
    except Exception as e:
        log.debug("Webhook: payload validation failed: %s", e)
        raise _error_response(web.HTTPBadRequest, "invalid payload")

    match payload.event_type:
        case "problem":
            return await _handle_problem(payload, argus, zabbix, config)
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
        log.warning(
            "Webhook: rejected request from %s: invalid or missing secret",
            request.remote,
        )
        raise _error_response(web.HTTPForbidden, "invalid secret")


def _validate_ip(request: web.Request, config: WebhookConfig):
    """Check the source IP against the allowlist."""
    if not config.allowed_ips:
        return
    remote = request.remote
    if remote is None:
        log.warning("Webhook: rejected request: could not determine remote address")
        raise _error_response(web.HTTPForbidden, "could not determine remote address")
    remote_addr = ipaddress.ip_address(remote)
    for entry in config.allowed_ips:
        if remote_addr in ipaddress.ip_network(entry, strict=False):
            return
    log.warning("Webhook: rejected request from %s: source IP not allowed", remote)
    raise _error_response(web.HTTPForbidden, "source IP not allowed")


async def _handle_problem(
    payload: WebhookPayload,
    argus: ArgusClient,
    zabbix: ZabbixClient,
    config: Config,
) -> web.Response:
    """Create an Argus incident from a Zabbix problem event.

    The Zabbix webhook payload carries no host-group data, so when the
    host-group filter or hostgroup tagging is active we look the host's
    groups up via the Zabbix API (cached).  Out-of-group problems are
    ignored so this path stays consistent with reconciliation.
    """
    hostgroups = (
        await zabbix.get_hostgroups_for_host(payload.hostname)
        if config.requires_hostgroups()
        else []
    )
    if not config.filter.allows(hostgroups):
        log.info(
            "Webhook: problem %s host %s not in allowed groups, ignoring",
            payload.eventid,
            payload.hostname,
        )
        return web.json_response({"status": "ignored"})

    argus_level = config.severity.mapping.get(payload.severity, 5)

    tags = build_tags(
        hostname=payload.hostname,
        hostgroups=hostgroups,
        trigger=payload.name,
        zabbix_tags=payload.tags,
        config=config.tags,
    )

    details_url = build_details_url(
        eventid=payload.eventid, triggerid=payload.triggerid
    )

    try:
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
    except DuplicateIncidentError:
        existing = await argus.get_incident_by_source_id(payload.eventid)
        log.info("Webhook: %s", describe_existing_incident(payload.eventid, existing))
        return web.json_response({"status": "duplicate"})
    except Exception:
        log.exception(
            "Webhook: failed to create incident for problem %s", payload.eventid
        )
        raise _error_response(web.HTTPInternalServerError, "argus error")

    log.debug("Webhook: created incident for problem %s", payload.eventid)
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
    try:
        resolved = await argus.resolve_by_source_id(payload.eventid)
    except Exception:
        log.exception(
            "Webhook: failed to resolve incident for problem %s", payload.eventid
        )
        raise _error_response(web.HTTPInternalServerError, "argus error")

    if resolved:
        log.info("Webhook: resolved incident for problem %s", payload.eventid)
        return web.json_response({"status": "resolved"})
    else:
        log.info("Webhook: no open incident found for problem %s", payload.eventid)
        return web.json_response({"status": "not_found"})


def _error_response(status_cls, message: str):
    """Build an aiohttp HTTP error with a JSON error body."""
    return status_cls(
        text=json.dumps({"error": message}),
        content_type="application/json",
    )


def _access_log_format(real_ip_header: str) -> str:
    """Build the aiohttp access-log format string.

    Defaults to aiohttp's standard format.  When ``real_ip_header`` is
    set (e.g. behind a reverse proxy that forwards the client IP), the
    client field is taken from that request header instead of the peer
    address, so logs show the real client rather than the proxy.
    """
    client = f"%{{{real_ip_header}}}i" if real_ip_header else "%a"
    return f'{client} %t "%r" %s %b "%{{Referer}}i" "%{{User-Agent}}i"'
