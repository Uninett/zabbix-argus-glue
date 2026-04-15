"""Tag building from Zabbix problem data."""

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
            tags.append((ztag["tag"], ztag.get("value", "")))

    for static_tag in config.static:
        key, _, value = static_tag.partition("=")
        tags.append((key, value))

    return tags


def tags_to_argus_api(tags: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Convert tag pairs to Argus API format: ``[{"tag": "key=value"}]``."""
    return [{"tag": f"{key}={value}"} for key, value in tags]
