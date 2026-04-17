# zabbix-argus-glue

A [glue service](https://argus-server.readthedocs.io/en/latest/integrations/glue-services/index.html)
that synchronizes [Zabbix](https://www.zabbix.com/) 7.4+ problems with
[Argus](https://github.com/Uninett/Argus) incidents. It translates
Zabbix problem events into Argus incident state changes, keeping both
systems in sync.

> **Status:** Early development. The reconciliation poller is
> functional; webhook and ack sync are planned but not yet implemented.

## Architecture

Hybrid push + poll design:

```
┌─────────────┐   webhook POST    ┌──────────────────────┐   REST API   ┌───────────┐
│   Zabbix    │ ─ ─ ─ ─ ─ ─ ─ >   │  zabbix-argus-glue   │ ───────────> │   Argus   │
│   Server    │ <───────────────  │                      │ <─────────── │   Server  │
│             │   API polling     │  - Reconciliation    │              │           │
└─────────────┘                   │  - HTTP receiver  *  │              └───────────┘
                                  │  - Ack sync       *  │
                                  └──────────────────────┘
                                           * planned
```

1. **Reconciliation poller** — periodically fetches open problems from
   Zabbix, compares against Argus state, fixes drift. Full sync on
   startup. **(implemented)**
2. **Webhook receiver** — receive Zabbix webhook POSTs, create/close
   Argus incidents in near-real-time. **(planned)**
3. **Ack sync** — detect acknowledgements and closures made in Argus,
   write them back to Zabbix. **(planned)**

## Installation

This package depends on the `feature/async` branch of
[pyargus](yhttps://github.com/Uninett/pyargus), which has not been
released to PyPI yet. Install directly from the repository:

```bash
pip install git+https://github.com/Uninett/zabbix-argus-glue.git
```

## Configuration

Copy the example configuration and edit it:

```bash
cp zabbixargus.example.toml zabbixargus.toml
```

See [zabbixargus.example.toml](zabbixargus.example.toml) for all
available options with comments.

The program searches for `zabbixargus.toml` in the following locations
(first match wins):

1. Current working directory
2. `$XDG_CONFIG_HOME/zabbixargus/` (typically `~/.config/zabbixargus/`)
3. System config directory (typically `/etc/xdg/zabbixargus/`)

You can override this with `--config PATH`.

API tokens can also be provided via the `ARGUS_TOKEN` and `ZABBIX_TOKEN`
environment variables instead of storing them in the config file.

Incident detail links point back to the Zabbix problem page using
relative URLs (e.g. `tr_events.php?triggerid=...&eventid=...`). The
Argus source system's `base_url` must include the full path prefix to
the Zabbix frontend — for Apache-based installs this is typically
`https://zabbix.example.com/zabbix/`, while Nginx-based installs
usually use `https://zabbix.example.com/`.

## Usage

```bash
# Run the service (config auto-discovered)
zabbix-argus-glue

# Verify API connectivity before running
zabbix-argus-glue --verify

# Use an explicit config file
zabbix-argus-glue --config /etc/zabbixargus/zabbixargus.toml

# Enable debug logging
zabbix-argus-glue -v
```

## Development

Requires Python 3.11+.

```bash
# Clone and install in editable mode
git clone https://github.com/Uninett/zabbix-argus-glue.git
cd zabbix-argus-glue
uv venv --python 3.13
uv sync --all-groups

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
