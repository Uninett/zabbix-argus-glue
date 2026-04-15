"""Synchronizes Zabbix problems with Argus incidents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zabbix-argus-glue")
except PackageNotFoundError:
    __version__ = "unknown"


def main():
    """Entry point for the zabbix-argus-glue CLI."""
    print(f"zabbix-argus-glue {__version__}")
    raise SystemExit("Not yet implemented")
