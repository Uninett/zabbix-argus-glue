"""Tests for tag building from Zabbix problem data."""

from zabbixargus.config import TagsConfig
from zabbixargus.tags import build_tags


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


class TestBuildTags:
    def test_when_all_fields_present_then_it_should_include_all(self):
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

    def test_when_host_disabled_then_it_should_skip_host(self):
        tags = build_tags(hostname="web01", config=_config(include_host=False))

        assert not any(k == "host" for k, _ in tags)

    def test_when_hostgroups_disabled_then_it_should_skip_hostgroups(self):
        tags = build_tags(
            hostgroups=["Linux servers"],
            config=_config(include_hostgroups=False),
        )

        assert not any(k == "hostgroup" for k, _ in tags)

    def test_when_multiple_hostgroups_then_it_should_create_one_per_group(self):
        tags = build_tags(
            hostgroups=["Linux servers", "Web servers"],
            config=_config(),
        )

        hostgroup_tags = [(k, v) for k, v in tags if k == "hostgroup"]
        assert len(hostgroup_tags) == 2
        assert ("hostgroup", "Linux servers") in hostgroup_tags
        assert ("hostgroup", "Web servers") in hostgroup_tags

    def test_when_trigger_disabled_then_it_should_skip_trigger(self):
        tags = build_tags(trigger="High CPU", config=_config(include_trigger=False))

        assert not any(k == "trigger" for k, _ in tags)

    def test_when_zabbix_tags_disabled_then_it_should_skip_them(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "app", "value": "nginx"}],
            config=_config(include_zabbix_tags=False),
        )

        assert not any(k == "app" for k, _ in tags)

    def test_when_zabbix_tag_has_no_value_then_it_should_use_empty_string(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "monitored"}],
            config=_config(),
        )

        assert ("monitored", "") in tags

    def test_when_static_tags_configured_then_it_should_append_them(self):
        tags = build_tags(config=_config(static=["source=zabbix", "env=prod"]))

        assert ("source", "zabbix") in tags
        assert ("env", "prod") in tags

    def test_when_no_data_provided_then_it_should_return_only_static(self):
        tags = build_tags(config=_config(static=["source=zabbix"]))

        assert tags == [("source", "zabbix")]

    def test_when_no_data_and_no_static_then_it_should_return_empty(self):
        tags = build_tags(config=_config())

        assert tags == []

    def test_when_zabbix_tag_has_uppercase_then_it_should_lowercase_key(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "Application", "value": "nginx"}],
            config=_config(),
        )

        assert ("application", "nginx") in tags

    def test_when_zabbix_tag_has_spaces_then_it_should_use_underscores(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "My Tag", "value": "val"}],
            config=_config(),
        )

        assert ("my_tag", "val") in tags

    def test_when_zabbix_tag_has_hyphens_then_it_should_use_underscores(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "my-tag", "value": "val"}],
            config=_config(),
        )

        assert ("my_tag", "val") in tags

    def test_when_zabbix_tag_has_dots_then_it_should_strip_them(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "net.if.speed", "value": "1000"}],
            config=_config(),
        )

        assert ("netifspeed", "1000") in tags

    def test_when_zabbix_tag_sanitizes_to_empty_then_it_should_skip_it(self):
        tags = build_tags(
            zabbix_tags=[{"tag": "!!!", "value": "bad"}],
            config=_config(),
        )

        assert not any(v == "bad" for _, v in tags)

    def test_when_allowlist_set_then_it_should_only_include_allowed(self):
        tags = build_tags(
            zabbix_tags=[
                {"tag": "application", "value": "nginx"},
                {"tag": "team", "value": "ops"},
            ],
            config=_config(zabbix_tag_allow=["application"]),
        )

        assert ("application", "nginx") in tags
        assert not any(k == "team" for k, _ in tags)

    def test_when_blocklist_set_then_it_should_exclude_blocked(self):
        tags = build_tags(
            zabbix_tags=[
                {"tag": "application", "value": "nginx"},
                {"tag": "host", "value": "web01"},
            ],
            config=_config(zabbix_tag_block=["host"]),
        )

        assert ("application", "nginx") in tags
        assert not any(k == "host" and v == "web01" for k, v in tags)

    def test_when_both_allow_and_block_set_then_allowlist_should_take_precedence(self):
        tags = build_tags(
            zabbix_tags=[
                {"tag": "application", "value": "nginx"},
                {"tag": "service", "value": "web"},
            ],
            config=_config(
                zabbix_tag_allow=["application"],
                zabbix_tag_block=["application"],
            ),
        )

        assert ("application", "nginx") in tags
        assert not any(k == "service" for k, _ in tags)
