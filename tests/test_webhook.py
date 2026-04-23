"""Tests for the webhook receiver."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from zabbixargus.config import (
    ArgusConfig,
    Config,
    TagsConfig,
    WebhookConfig,
    ZabbixConfig,
)
from zabbixargus.webhook import create_app


def _config(**overrides):
    defaults = dict(
        argus=ArgusConfig(url="https://argus", token="t"),
        zabbix=ZabbixConfig(url="https://zabbix", token="t"),
        webhook=WebhookConfig(secret="test-secret"),
        tags=TagsConfig(static=["source=zabbix"]),
    )
    defaults.update(overrides)
    return Config(**defaults)


def _problem_payload(**overrides):
    defaults = dict(
        eventid="123",
        value="1",
        severity="4",
        hostname="web01",
        name="High CPU usage",
        clock="2026.04.22 12:00:00",
        triggerid="456",
        tags=json.dumps([{"tag": "application", "value": "nginx"}]),
    )
    defaults.update(overrides)
    return defaults


def _update_payload(**overrides):
    defaults = dict(
        eventid="123",
        value="1",
        update_status="1",
        update_action=json.dumps({"acknowledge": True, "message": "ack from Zabbix"}),
        update_user="Admin Admin",
    )
    defaults.update(overrides)
    return defaults


def _resolution_payload(**overrides):
    defaults = dict(eventid="123", value="0")
    defaults.update(overrides)
    return defaults


@pytest.fixture
def mock_argus():
    argus = MagicMock()
    argus.create_incident_from_problem = AsyncMock()
    argus.resolve_by_source_id = AsyncMock(return_value=True)
    return argus


@pytest.fixture
async def client(mock_argus):
    config = _config()
    app = create_app(mock_argus, config)
    async with TestClient(TestServer(app)) as c:
        yield c


async def _post(client, payload=None, headers=None):
    """POST to /webhook with the default secret header."""
    hdrs = {"X-Webhook-Secret": "test-secret"}
    if headers:
        hdrs.update(headers)
    return await client.post("/webhook", json=payload, headers=hdrs)


class TestValidateRequest:
    async def test_when_secret_missing_then_it_should_return_403(self, client):
        resp = await client.post("/webhook", json=_problem_payload(), headers={})

        assert resp.status == 403

    async def test_when_secret_wrong_then_it_should_return_403(self, client):
        resp = await client.post(
            "/webhook",
            json=_problem_payload(),
            headers={"X-Webhook-Secret": "wrong"},
        )

        assert resp.status == 403

    async def test_when_secret_correct_then_it_should_accept(self, client, mock_argus):
        resp = await _post(client, _problem_payload())

        assert resp.status == 201

    async def test_when_no_secret_configured_then_it_should_accept_any(
        self, mock_argus
    ):
        config = _config(webhook=WebhookConfig(secret=""))
        app = create_app(mock_argus, config)
        async with TestClient(TestServer(app)) as c:
            resp = await c.post("/webhook", json=_problem_payload())

        assert resp.status == 201

    async def test_when_ip_not_in_allowlist_then_it_should_return_403(self, mock_argus):
        config = _config(
            webhook=WebhookConfig(secret="test-secret", allowed_ips=["192.168.1.0/24"])
        )
        app = create_app(mock_argus, config)
        async with TestClient(TestServer(app)) as c:
            resp = await _post(c, _problem_payload())

        assert resp.status == 403

    async def test_when_ip_in_allowlist_then_it_should_accept(self, mock_argus):
        config = _config(
            webhook=WebhookConfig(secret="test-secret", allowed_ips=["127.0.0.0/8"])
        )
        app = create_app(mock_argus, config)
        async with TestClient(TestServer(app)) as c:
            resp = await _post(c, _problem_payload())

        assert resp.status == 201


class TestHandleProblem:
    async def test_when_problem_received_then_it_should_create_incident(
        self, client, mock_argus
    ):
        resp = await _post(client, _problem_payload())

        assert resp.status == 201
        mock_argus.create_incident_from_problem.assert_awaited_once()

    async def test_when_problem_received_then_it_should_pass_correct_fields(
        self, client, mock_argus
    ):
        await _post(client, _problem_payload())

        call_kwargs = mock_argus.create_incident_from_problem.call_args.kwargs
        assert call_kwargs["source_incident_id"] == "123"
        assert call_kwargs["hostname"] == "web01"
        assert call_kwargs["description"] == "High CPU usage"
        assert call_kwargs["level"] == 2  # severity 4 → Argus level 2
        assert "triggerid=456" in call_kwargs["details_url"]
        assert "eventid=123" in call_kwargs["details_url"]

    async def test_when_tags_json_string_then_it_should_parse_tags(
        self, client, mock_argus
    ):
        await _post(client, _problem_payload())

        call_kwargs = mock_argus.create_incident_from_problem.call_args.kwargs
        assert ("application", "nginx") in call_kwargs["tags"]

    async def test_when_tags_invalid_json_then_it_should_skip_tags(
        self, client, mock_argus
    ):
        payload = _problem_payload(tags="not-json")

        await _post(client, payload)

        call_kwargs = mock_argus.create_incident_from_problem.call_args.kwargs
        # Should still have host tag and static tags, just no zabbix tags
        assert ("host", "web01") in call_kwargs["tags"]

    async def test_when_severity_unknown_then_it_should_default_to_5(
        self, client, mock_argus
    ):
        payload = _problem_payload(severity="99")

        await _post(client, payload)

        call_kwargs = mock_argus.create_incident_from_problem.call_args.kwargs
        assert call_kwargs["level"] == 5


class TestHandleResolution:
    async def test_when_resolution_received_then_it_should_resolve_incident(
        self, client, mock_argus
    ):
        resp = await _post(client, _resolution_payload())

        assert resp.status == 200
        mock_argus.resolve_by_source_id.assert_awaited_once_with("123")

    async def test_when_no_matching_incident_then_it_should_return_not_found(
        self, client, mock_argus
    ):
        mock_argus.resolve_by_source_id.return_value = False

        resp = await _post(client, _resolution_payload())
        body = await resp.json()

        assert resp.status == 200
        assert body["status"] == "not_found"


class TestHandleUpdate:
    async def test_when_update_received_then_it_should_return_200(self, client):
        resp = await _post(client, _update_payload())

        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "update_received"

    async def test_when_update_received_then_it_should_not_create_incident(
        self, client, mock_argus
    ):
        await _post(client, _update_payload())

        mock_argus.create_incident_from_problem.assert_not_awaited()

    async def test_when_update_received_then_it_should_not_resolve_incident(
        self, client, mock_argus
    ):
        await _post(client, _update_payload())

        mock_argus.resolve_by_source_id.assert_not_awaited()

    async def test_when_update_action_is_json_string_then_it_should_parse(self, client):
        payload = _update_payload(
            update_action=json.dumps({"acknowledge": True, "close": False})
        )

        resp = await _post(client, payload)

        assert resp.status == 200


class TestPayloadValidation:
    async def test_when_invalid_json_then_it_should_return_400(self, client):
        resp = await client.post(
            "/webhook",
            data=b"not json",
            headers={
                "X-Webhook-Secret": "test-secret",
                "Content-Type": "application/json",
            },
        )

        assert resp.status == 400

    async def test_when_eventid_missing_then_it_should_return_400(self, client):
        resp = await _post(client, {"value": "1"})

        assert resp.status == 400

    async def test_when_value_invalid_then_it_should_return_400(self, client):
        resp = await _post(client, {"eventid": "123", "value": "2"})

        assert resp.status == 400

    async def test_when_validation_fails_then_error_body_should_be_generic(
        self, client
    ):
        resp = await _post(client, {"value": "1"})
        body = await resp.json()

        assert body == {"error": "invalid payload"}

    async def test_when_get_request_then_it_should_return_405(self, client):
        resp = await client.get("/webhook", headers={"X-Webhook-Secret": "test-secret"})

        assert resp.status == 405


class TestArgusFailure:
    async def test_when_argus_create_raises_then_it_should_return_500(
        self, client, mock_argus
    ):
        mock_argus.create_incident_from_problem.side_effect = Exception("network")

        resp = await _post(client, _problem_payload())

        assert resp.status == 500

    async def test_when_argus_resolve_raises_then_it_should_return_500(
        self, client, mock_argus
    ):
        mock_argus.resolve_by_source_id.side_effect = Exception("network")

        resp = await _post(client, _resolution_payload())

        assert resp.status == 500


class TestClockParsing:
    async def test_when_clock_unparseable_then_it_should_fall_back(
        self, client, mock_argus
    ):
        payload = _problem_payload(clock="not a date")

        resp = await _post(client, payload)

        assert resp.status == 201
        # Fallback produces a recent datetime; just verify it was accepted
        call_kwargs = mock_argus.create_incident_from_problem.call_args.kwargs
        assert call_kwargs["start_time"] is not None
