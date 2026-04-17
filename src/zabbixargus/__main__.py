"""CLI entry point for zabbix-argus-glue."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from zabbixargus import __version__
from zabbixargus.config import load_config

log = logging.getLogger("zabbixargus")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Synchronizes Zabbix problems with Argus incidents",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="path to TOML configuration file",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="test API connectivity and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"zabbix-argus-glue {__version__}",
    )
    return parser.parse_args(argv)


async def verify_zabbix(config):
    """Verify Zabbix API connectivity. Returns True on success."""
    raise NotImplementedError


async def verify_argus(config):
    """Verify Argus API connectivity. Returns True on success."""
    raise NotImplementedError


async def verify_connections(config):
    """Test connectivity to both Zabbix and Argus APIs."""
    zabbix_ok = await verify_zabbix(config)
    argus_ok = await verify_argus(config)
    return zabbix_ok and argus_ok


def cli(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    if args.verify:
        ok = asyncio.run(verify_connections(config))
        sys.exit(0 if ok else 1)

    # Default: run the service
    print(f"zabbix-argus-glue {__version__}")
    raise SystemExit("Service run loop not yet implemented")
