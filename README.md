# netbox2prom

Generates monitoring configurations from NetBox data. Polls the NetBox API and produces configuration files for Prometheus (SNMP exporter) and Alloy (Blackbox ICMP checks).

## Features

- **Prometheus** — generates scrape configs for SNMP exporter (per device group)
- **probe_icmp** — generates JSON targets for Blackbox ICMP checks (device reachability)
- **probe_http** — generates JSON targets for Blackbox HTTP checks (website availability from NetBox services)
- Each generator can be independently toggled via environment variables
- Container runs as a long-running poll loop or in single-run mode
- All rules are declarative in YAML config

## Quick start

### Docker

```bash
# 1. Prepare config
cp config.example.yml config.yml
# Edit config.yml: set NetBox URL, paths, and rules

# 2. Set token
export NETBOX_TOKEN="your-read-only-api-token"

# 3. Run
docker compose up -d
```

### Without Docker

```bash
pip install -r requirements.txt
export NETBOX_TOKEN="your-read-only-api-token"
export NETBOX2PROM_CONFIG="./config.yml"

# Single run
RUN_ONCE=true python -m netbox2prom

# Or in loop mode
python -m netbox2prom
```

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `NETBOX_TOKEN` | NetBox API token (read-only) | — (required) |
| `NETBOX2PROM_CONFIG` | Path to config file | `/etc/netbox2prom/config.yml` |
| `ENABLE_PROMETHEUS` | Enable Prometheus generator | `true` |
| `ENABLE_PROBE_ICMP` | Enable probe_icmp generator (ICMP blackbox) | `true` |
| `ENABLE_PROBE_HTTP` | Enable probe_http generator (HTTP blackbox) | `true` |
| `ENABLE_SYSLOG` | Enable syslog-ng generator | `false` |
| `POLL_INTERVAL` | Poll interval in seconds | `300` |
| `RUN_ONCE` | Run once and exit | `false` |
| `LOG_LEVEL` | Log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) | `INFO` |

> If none of the `ENABLE_*` variables are set, all generators are enabled. At least one must be enabled — the container will refuse to start otherwise. `ENABLE_ALLOY` is accepted as a backwards-compatible alias for `ENABLE_PROBE_ICMP`.

## Documentation

Detailed guides live in the [`docs/`](docs/) folder:

| Guide | Description |
|---|---|
| [NetBox Setup](docs/netbox-setup.md) | API token, custom fields (`snmp_ver`, `snmp_cipher`, `criticality`), config contexts, tags, and the NetBox device fields read by the service |
| [Configuration Reference](docs/configuration.md) | Full YAML reference: all condition types (`exact`, `list`, `not_null`, `null`, `any_except`, `not_in`, `tags_contains`), placeholders, and group options for every generator |
| [Receiver Setup](docs/receivers-setup.md) | Prometheus (`scrape_config_files`, snmp_exporter, reload), Alloy (`discovery.file`, blackbox exporter, relabel for ICMP + HTTP), and syslog-ng (rewrite blocks, template syntax) |

Configuration is stored in a YAML file — see [`config.example.yml`](config.example.yml) for a full annotated example. The NetBox token is passed exclusively via the `NETBOX_TOKEN` environment variable.

## Building the Docker image

```bash
docker build -t hamptik/netbox2prom .
```
