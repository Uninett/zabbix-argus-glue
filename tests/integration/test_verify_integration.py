"""Integration test for Argus connectivity verification against a live server."""

import pytest

from zabbixargus.__main__ import verify_argus
from zabbixargus.config import ArgusConfig, Config, ZabbixConfig

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_when_live_argus_then_verify_argus_should_succeed(
    argus_api_url, argus_source_system_token
):
    config = Config(
        argus=ArgusConfig(url=argus_api_url, token=argus_source_system_token),
        zabbix=ZabbixConfig(url="https://unused", token="unused"),
    )

    result = await verify_argus(config)

    assert result is True
