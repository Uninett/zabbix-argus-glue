# zabbix-argus-glue

Synchronizes [Zabbix](https://www.zabbix.com/) 7.4+ problems with
[Argus](https://github.com/Uninett/Argus) incidents.

## Architecture

Hybrid push + poll design with three concurrent async loops:

```
┌─────────────┐   webhook POST    ┌──────────────────────┐   REST API    ┌───────────┐
│   Zabbix     │ ───────────────> │  zabbix-argus-glue   │ ───────────> │   Argus    │
│   Server     │ <─────────────── │                      │ <─────────── │   Server   │
│              │   API polling    │  - HTTP receiver     │              │            │
└─────────────┘   + ack writeback │  - Reconciliation    │              └───────────┘
                                  │  - Ack sync          │
                                  └──────────────────────┘
```

1. **Webhook receiver** — receives Zabbix webhook POSTs, creates/closes
   Argus incidents in near-real-time.
2. **Reconciliation poller** — periodically fetches open problems from
   Zabbix, compares against Argus state, fixes drift. Full sync on startup.
3. **Ack sync** — detects acknowledgements and closures made in Argus,
   writes them back to Zabbix (optional, off by default).

## Installation

```bash
pip install zabbix-argus-glue
```

## Configuration

Create a TOML configuration file:

```toml
[argus]
url = "https://argus.example.com"
token = "abc123..."       # or set ARGUS_TOKEN env var

[zabbix]
url = "https://zabbix.example.com"
token = "xyz789..."       # or set ZABBIX_TOKEN env var

[webhook]
enabled = true
listen = "0.0.0.0"
port = 8080
secret = "shared-secret"

[reconciliation]
enabled = true
interval = 60
```

## Usage

```bash
zabbix-argus-glue --config config.toml
```

## Development

Requires Python 3.11+.

```bash
# Clone and install in editable mode
git clone https://github.com/Uninett/zabbix-argus-glue.git
cd zabbix-argus-glue
uv venv
uv pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install

# Run tests
pytest

# Lint and format
ruff check --fix src/
ruff format src/
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md). We use
[towncrier](https://towncrier.readthedocs.io/) to manage changelog
fragments. Add a fragment to `changelog.d/` with each PR.

## License

Apache-2.0. See [LICENSE](LICENSE).
