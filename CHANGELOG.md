# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [Unreleased]

Initial feature set, in preparation for the first alpha release.

### Added

- Webhook receiver that accepts Zabbix webhook POSTs and creates or closes
  Argus incidents in near-real-time, with shared-secret authentication,
  payload validation, and correct client-IP logging behind a reverse proxy.
- Reconciliation poller that periodically fetches open Zabbix problems,
  compares them against Argus incident state, and corrects drift, including a
  full sync on startup.
- Optional `[filter]` `hostgroups` allow-list that restricts which Zabbix
  problems are synced to Argus by host group, applied consistently across the
  webhook and reconciliation paths; host-group membership is emitted as
  `hostgroup` tags on incidents.
- Configuration discovery across the working directory and XDG config
  directories, with a `--config` override and `ARGUS_TOKEN` / `ZABBIX_TOKEN`
  environment variables for API credentials.
- `zabbix-argus-glue` command-line interface with a `--verify` connectivity
  check and verbose logging.
