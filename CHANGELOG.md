# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [0.1.2] - 2026-10-22

### Security

- Upgrade all locked dependencies, including anyio 4.15.1 (fixes
  CVE-2026-63374, TLS certificate spoofing) and aiohttp 3.14.5 (fixes several
  denial-of-service vulnerabilities).


## [0.1.1] - 2026-10-22

### Security

- Require certifi 2026.10.19 or newer in the locked dependencies, as older
  bundles still trust the compromised eMudhra/emSign root CA.


## [0.1.0] - 2026-06-30

Initial release.

### Added

- **Webhook receiver** that accepts Zabbix webhook POSTs and creates or
  closes Argus incidents in near-real-time. Supports shared-secret
  authentication (via `[webhook] secret` or the `WEBHOOK_SECRET`
  environment variable), payload validation, an optional IP allow-list,
  and logging of the real client IP behind a reverse proxy via
  `[webhook] real_ip_header`.
- **Reconciliation poller** that periodically fetches open Zabbix
  problems, compares them against Argus incident state, and corrects
  drift, with a full sync on startup. Resolved problems are re-confirmed
  before their incidents are closed, an empty problem fetch never closes
  incidents, and incidents Argus rejects as duplicates (e.g. operator
  force-closed) are handled and logged rather than raising errors.
- **Host-group filtering** via an optional `[filter] hostgroups`
  allow-list, applied consistently across the webhook and reconciliation
  paths. Host-group membership is emitted as `hostgroup` tags on
  incidents.
- **Incident close reasons** recorded on the closing event, so the Argus
  event log shows why an incident was resolved: `Resolved in Zabbix` when
  a Zabbix problem recovers, or `Resolved by reconciliation` when the
  reconciliation sweep cleans up drift.
- **Flexible configuration**: discovery across the working directory and
  XDG config directories, a `--config` override, and `ARGUS_TOKEN` /
  `ZABBIX_TOKEN` / `WEBHOOK_SECRET` environment variables so credentials
  need not live in a plaintext config file.
- **Command-line interface** (`zabbix-argus-glue`) with a `--verify`
  connectivity check and verbose logging.
