"""Synchronizes Zabbix problems with Argus incidents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zabbix-argus-glue")
except PackageNotFoundError:
    __version__ = "unknown"


def main():
    """Entry point for the zabbix-argus-glue CLI."""
    from zabbixargus.__main__ import cli

    cli()
