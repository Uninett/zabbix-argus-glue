"""Tests for tag building from Zabbix problem data."""

from zabbixargus.config import TagsConfig
from zabbixargus.tags import build_tags, tags_to_argus_api


def _config(**overrides) -> TagsConfig:
    defaults = dict(
        static=[],
        include_host=True,
        include_hostgroups=True,
        include_trigger=True,
        include_zabbix_tags=True,
    )
    defaults.update(overrides)
    return TagsConfig(**defaults)


def test_when_all_fields_present_then_build_tags_should_include_all():
    tags = build_tags(
        hostname="web01",
        hostgroups=["Linux servers"],
        trigger="High CPU",
        zabbix_tags=[{"tag": "app", "value": "nginx"}],
        config=_config(static=["source=zabbix"]),
    )

    assert ("host", "web01") in tags
    assert ("hostgroup", "Linux servers") in tags
    assert ("trigger", "High CPU") in tags
    assert ("app", "nginx") in tags
    assert ("source", "zabbix") in tags


def test_when_host_disabled_then_build_tags_should_skip_host():
    tags = build_tags(hostname="web01", config=_config(include_host=False))

    assert not any(k == "host" for k, _ in tags)


def test_when_hostgroups_disabled_then_build_tags_should_skip_hostgroups():
    tags = build_tags(
        hostgroups=["Linux servers"],
        config=_config(include_hostgroups=False),
    )

    assert not any(k == "hostgroup" for k, _ in tags)


def test_when_multiple_hostgroups_then_build_tags_should_create_one_per_group():
    tags = build_tags(
        hostgroups=["Linux servers", "Web servers"],
        config=_config(),
    )

    hostgroup_tags = [(k, v) for k, v in tags if k == "hostgroup"]
    assert len(hostgroup_tags) == 2
    assert ("hostgroup", "Linux servers") in hostgroup_tags
    assert ("hostgroup", "Web servers") in hostgroup_tags


def test_when_trigger_disabled_then_build_tags_should_skip_trigger():
    tags = build_tags(trigger="High CPU", config=_config(include_trigger=False))

    assert not any(k == "trigger" for k, _ in tags)


def test_when_zabbix_tags_disabled_then_build_tags_should_skip_them():
    tags = build_tags(
        zabbix_tags=[{"tag": "app", "value": "nginx"}],
        config=_config(include_zabbix_tags=False),
    )

    assert not any(k == "app" for k, _ in tags)


def test_when_zabbix_tag_has_no_value_then_build_tags_should_use_empty_string():
    tags = build_tags(
        zabbix_tags=[{"tag": "monitored"}],
        config=_config(),
    )

    assert ("monitored", "") in tags


def test_when_static_tags_configured_then_build_tags_should_append_them():
    tags = build_tags(config=_config(static=["source=zabbix", "env=prod"]))

    assert ("source", "zabbix") in tags
    assert ("env", "prod") in tags


def test_when_no_data_provided_then_build_tags_should_return_only_static():
    tags = build_tags(config=_config(static=["source=zabbix"]))

    assert tags == [("source", "zabbix")]


def test_when_no_data_and_no_static_then_build_tags_should_return_empty():
    tags = build_tags(config=_config())

    assert tags == []


def test_tags_to_argus_api_should_produce_correct_format():
    tags = [("host", "web01"), ("hostgroup", "Linux servers")]

    result = tags_to_argus_api(tags)

    assert result == [
        {"tag": "host=web01"},
        {"tag": "hostgroup=Linux servers"},
    ]
