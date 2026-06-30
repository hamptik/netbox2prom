# netbox2prom

Generates monitoring configurations from NetBox data. Polls the NetBox API and produces configuration files for Prometheus (SNMP exporter) and Alloy (Blackbox ICMP checks).

## Features

- **Prometheus** — generates scrape configs for SNMP exporter (per device group)
- **Alloy / Blackbox** — generates JSON targets for ICMP checks
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
| `ENABLE_ALLOY` | Enable Alloy generator | `true` |
| `ENABLE_SYSLOG` | Enable syslog-ng generator | `false` |
| `POLL_INTERVAL` | Poll interval in seconds | `300` |
| `RUN_ONCE` | Run once and exit | `false` |
| `LOG_LEVEL` | Log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`) | `INFO` |

> If none of the `ENABLE_*` variables are set, both Prometheus and Alloy generators are enabled. At least one must be enabled — the container will refuse to start otherwise.

## Configuration

Configuration is stored in a YAML file (`config.example.yml` is a full example). The NetBox token is passed exclusively via the `NETBOX_TOKEN` environment variable.

### Structure

```yaml
netbox:
  url: "https://netbox.example.com"
  tag: monitoring

prometheus:
  snmp_exporter_address: "snmp-exporter:9116"
  metrics_path: /snmp
  scrape_dir: /opt/configs/prometheus-scrape
  reload_address: "http://prometheus:9090"
  default_labels:
    instance: "{name}"
    criticality: "{criticality}"
  groups:
    my_job:
      conditions: { ... }
      params: { ... }
      ip_field: main_ip

alloy:
  targets_file: /etc/alloy/blackbox_targets.json
  default_labels:
    __param_module: icmp
    environment: prod
  groups:
    my_rule:
      conditions: { ... }
      target_field: main_ip
      labels: { ... }

syslog:
  config_file: /etc/syslog-ng/conf.d/netbox2prom.conf
  block_name: fix_hostnames
  reload:
    method: http
    address: "http://syslog-ng:601"
  groups:
    my_group:
      conditions: { ... }
      host_field: main_ip
      template: |-
            set("{name}", value("PROGRAM") \
                condition("${HOST}" eq "{ip}"));
```

### Device matching conditions

Conditions are declarative rules for matching devices. Supported types:

| Value | Semantics |
|---|---|
| `vendor: dell` | Exact match (string comparison) |
| `role: [switch, router]` | Value is in list |
| `main_ip: not_null` | Field is populated |
| `oob_ip: null` | Field is empty |
| `vendor: any_except` + `vendor_exclude: [...]` | Populated and not in exclude list |
| `vendor: not_in` + `vendor_exclude: [...]` | Not in exclude list (empty field passes) |
| `tags_contains: [management]` | Device has at least one of the specified tags |
| `snmp_ver: 3` | Exact numeric match |
| `virtual: false` | Boolean comparison |

### Label placeholders

In `default_labels`, `labels` (alloy), and `template` (syslog), you can use placeholders:

| Placeholder | Value |
|---|---|
| `{name}` | Device name (with `name_prefix`/`name_suffix` applied) |
| `{target_ip}` | Target IP address (from `target_field`/`ip_field`) |
| `{device_label}` | `virtual` or `device` |
| `{criticality}` | Custom field `criticality` value |
| `{os_type}` / `{os}` | OS from config context |
| `{main_ip}` / `{oob_ip}` | Corresponding IP |
| `{vendor}` / `{model}` / `{role}` | Slug values |
| `{snmp_ver}` | SNMP version |

> In syslog templates, `{name}`, `{ip}` and other placeholders are substituted directly. Syslog-ng macros like `${HOST}` are left untouched — no escaping needed.

### Alloy group options

| Option | Description |
|---|---|
| `target_field` | Device field to use as IP (`main_ip`, `oob_ip`) |
| `exclusive: true` | On match, skip remaining rules for this device |
| `name_prefix` / `name_suffix` | Prepend/append to device name |

## NetBox setup

### Custom fields (DCIM -> Device)

| Slug | Type | Values |
|---|---|---|
| `snmp_ver` | Integer | 0-3, default 0 |
| `snmp_cipher` | Selection | aes/des |
| `criticality` | Selection or Text | your choice |

### Config context

Create config contexts for Linux/Windows platforms to populate the OS field:

```json
{ "os": "linux" }
```

### Tag

| Slug | Object types |
|---|---|
| `monitoring` | Device, Virtual Machine |

## Receiver setup

### Prometheus

In `prometheus.yml`:

```yaml
scrape_config_files:
  - '/opt/configs/prometheus-scrape/*.yml'
```

### Alloy

```alloy
discovery.file "icmp" {
  files = ["/etc/alloy/blackbox_targets.json"]
  refresh_interval = "30s"
}

prometheus.exporter.blackbox "icmp" {
  config_file = "/etc/alloy/blackbox_modules.yml"
  targets     = discovery.file.icmp.targets
}

discovery.relabel "icmp" {
  targets = prometheus.exporter.blackbox.icmp.targets

  rule {
    source_labels = ["__param_target"]
    target_label = "instance"
  }

  rule {
    source_labels = ["name"]
    target_label = "target_name"
  }
}
```

### Syslog-ng

The tool generates a standalone file in `conf.d/` that it fully owns. Make sure syslog-ng includes it and references the rewrite rule:

```syslog-ng
# In syslog-ng.conf — include managed files:
@include "/etc/syslog-ng/conf.d/*.conf"

# Apply the rewrite rule in your log path:
log {
    source(s_net);
    rewrite(fix_hostnames);
    destination(d_all);
};
```

Reload is triggered automatically after each config update. Configure the method under `syslog.reload`:

| Method | Config | Use case |
|---|---|---|
| `http` | `address: "http://syslog-ng:601"` | Container sidecar / remote syslog-ng with HTTP API |
| `signal` | `pid_file: /var/run/syslog-ng.pid` | Same host or shared PID namespace |
| `command` | `command: "syslog-ng-ctl reload"` | Flexible — any shell command |
| `none` | — | External watcher handles reload (inotify, etc.) |

## Building the Docker image

```bash
docker build -t hamptik/netbox2prom .
```
