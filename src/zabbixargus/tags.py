"""Tag building from Zabbix problem data."""

import re

from zabbixargus.config import TagsConfig


def build_tags(
    *,
    hostname: str = "",
    hostgroups: list[str] | None = None,
    trigger: str = "",
    zabbix_tags: list[dict[str, str]] | None = None,
    config: TagsConfig,
) -> list[tuple[str, str]]:
    """Build Argus tags from Zabbix problem data.

    Zabbix tags are expected as ``[{"tag": "key", "value": "val"}, ...]``.
    Returns a list of (key, value) pairs.  Duplicate keys are allowed
    (e.g. multiple hostgroups).
    """
    tags: list[tuple[str, str]] = []

    if config.include_host and hostname:
        tags.append(("host", hostname))

    if config.include_hostgroups and hostgroups:
        for group in hostgroups:
            tags.append(("hostgroup", group))

    if config.include_trigger and trigger:
        tags.append(("trigger", trigger))

    if config.include_zabbix_tags and zabbix_tags:
        for ztag in zabbix_tags:
            key = _sanitize_key(ztag["tag"])
            if key and _is_tag_allowed(key, config):
                tags.append((key, ztag.get("value", "")))

    for static_tag in config.static:
        key, _, value = static_tag.partition("=")
        tags.append((key, value))

    return tags


def _sanitize_key(key: str) -> str:
    """Sanitize a tag key for Argus compatibility.

    Argus requires keys to match ``^[a-z0-9_]+$``.  Returns an empty
    string if nothing remains after sanitization.
    """
    key = key.lower().replace(" ", "_").replace("-", "_")
    return re.sub(r"[^a-z0-9_]", "", key)


def _is_tag_allowed(key: str, config: TagsConfig) -> bool:
    """Check whether a sanitized Zabbix tag key passes the filter."""
    if config.zabbix_tag_allow:
        return key in config.zabbix_tag_allow
    return key not in config.zabbix_tag_block
