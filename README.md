# zabbix-argus-glue

A [glue service](https://argus-server.readthedocs.io/en/latest/integrations/glue-services/index.html)
that synchronizes [Zabbix](https://www.zabbix.com/) 7.4+ problems with
[Argus](https://github.com/Uninett/Argus) incidents. It translates
Zabbix problem events into Argus incident state changes, keeping both
systems in sync.

> **Status:** Early development. The reconciliation poller and webhook
> receiver are functional; ack sync is planned but not yet implemented.

## Architecture

Hybrid push + poll design:

```
┌─────────────┐   webhook POST    ┌──────────────────────┐   REST API   ┌───────────┐
│   Zabbix    │ ───────────────>  │  zabbix-argus-glue   │ ───────────> │   Argus   │
│   Server    │ <───────────────  │                      │ <─────────── │   Server  │
│             │   API polling     │  - HTTP receiver     │              │           │
└─────────────┘                   │  - Reconciliation    │              └───────────┘
                                  │  - Ack sync       *  │
                                  └──────────────────────┘
                                           * planned
```

1. **Webhook receiver** — receives Zabbix webhook POSTs, creates/closes
   Argus incidents in near-real-time. **(implemented)**
2. **Reconciliation poller** — periodically fetches open problems from
   Zabbix, compares against Argus state, fixes drift. Full sync on
   startup. **(implemented)**
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

## Webhook setup

The webhook receiver listens for HTTP POSTs from Zabbix. To use it,
you need to configure a webhook media type and a trigger action in
Zabbix.

### 1. Create a webhook media type

In Zabbix, go to **Alerts → Media types → Create media type** and
configure:

- **Name:** `Argus`
- **Type:** Webhook
- **Parameters:**

  | Name        | Value                                               |
  |-------------|-----------------------------------------------------|
  | `glue_url`  | `http://glue-host:8080/webhook`                     |
  | `secret`    | *(same value as `[webhook] secret` in your config)* |
  | `eventid`   | `{EVENT.ID}`                                        |
  | `value`     | `{EVENT.VALUE}`                                     |
  | `severity`  | `{EVENT.NSEVERITY}`                                 |
  | `hostname`  | `{HOST.NAME}`                                       |
  | `name`      | `{EVENT.NAME}`                                      |
  | `clock`     | `{EVENT.DATE} {EVENT.TIME}`                         |
  | `triggerid` | `{TRIGGER.ID}`                                      |
  | `tags`      | `{EVENT.TAGSJSON}`                                  |

- **Script:**

  ```js
  var params = JSON.parse(value),
      req = new HttpRequest(),
      payload = {};

  req.addHeader('Content-Type: application/json');
  req.addHeader('X-Webhook-Secret: ' + params.secret);

  payload.eventid = params.eventid;
  payload.value = params.value;
  payload.severity = params.severity;
  payload.hostname = params.hostname;
  payload.name = params.name;
  payload.clock = params.clock;
  payload.triggerid = params.triggerid;
  payload.tags = params.tags;

  var resp = req.post(params.glue_url, JSON.stringify(payload));

  if (req.getStatus() < 200 || req.getStatus() >= 300) {
      throw 'Request failed with status ' + req.getStatus()
          + ': ' + resp;
  }

  return 'OK';
  ```

### 2. Assign the media type to a user

Zabbix sends alerts through users. Create a dedicated service
account or use an existing user.

Go to **Users → Users** and create or edit a user:

- **Username:** e.g. `argus-glue`
- **Groups:** A group with read access to the hosts you want to sync
- **Media tab → Add:**
  - **Type:** `Argus`
  - **Send to:** `argus` *(required by Zabbix but ignored by webhooks)*
  - **Enabled:** checked

### 3. Create a trigger action

Go to **Alerts → Actions → Trigger actions → Create action**:

- **Name:** `Send to Argus`
- **Conditions:** *(adjust to match the problems you want to sync)*
- **Operations → Add:**
  - **Send to users:** select the user from step 2
  - **Send only to:** `Argus`
  - Check **Custom message** and set any non-empty subject and
    body (e.g. `{EVENT.NAME}` / `{EVENT.ID}`). Zabbix requires a
    message to be defined even though webhooks ignore it.
- **Recovery operations → Add:**
  - Same settings as above, including a custom message

### 4. Test with curl

```bash
curl -X POST http://localhost:8080/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: your-secret' \
  -d '{
    "eventid": "12345",
    "value": "1",
    "severity": "4",
    "hostname": "web01.example.com",
    "name": "High CPU usage on web01",
    "clock": "2026.04.22 12:00:00",
    "triggerid": "678",
    "tags": "[{\"tag\": \"application\", \"value\": \"nginx\"}]"
  }'
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
