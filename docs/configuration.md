# Configuration Reference

Complete reference for the `config.yml` file. The full annotated example is in [`config.example.yml`](../config.example.yml).

---

## Table of Contents

- [File Structure](#file-structure)
- [netbox](#netbox)
- [prometheus](#prometheus)
- [probe_icmp](#probe_icmp)
- [probe_http](#probe_http)
- [syslog](#syslog)
- [Conditions](#conditions)
  - [Exact match](#exact-match)
  - [List match](#list-match)
  - [not_null](#not_null)
  - [null](#null)
  - [any_except](#any_except)
  - [not_in](#not_in)
  - [tags_contains](#tags_contains)
  - [Numeric match](#numeric-match)
  - [Boolean match](#boolean-match)
  - [Condition normalization](#condition-normalization)
  - [Multi-field exclude lists](#multi-field-exclude-lists)
  - [Combining conditions](#combining-conditions)
  - [Conditions quick reference](#conditions-quick-reference)
- [Placeholders](#placeholders)
- [probe_icmp group options](#probe_icmp-group-options)
- [probe_http group options](#probe_http-group-options)
- [Prometheus group options](#prometheus-group-options)
- [Syslog group options](#syslog-group-options)

---

## File Structure

```yaml
netbox:
  # NetBox connection settings

prometheus:
  # SNMP scrape config generation (enabled via ENABLE_PROMETHEUS=true)

probe_icmp:
  # Blackbox ICMP target generation from devices (enabled via ENABLE_PROBE_ICMP=true)

probe_http:
  # Blackbox HTTP target generation from NetBox services (enabled via ENABLE_PROBE_HTTP=true)

syslog:
  # syslog-ng rewrite rule generation (enabled via ENABLE_SYSLOG=true)
```

Each top-level section is independent. You only need to include sections for generators you actually use.

---

## netbox

Controls how the service connects to the NetBox API.

```yaml
netbox:
  url: "https://netbox.example.com"
  tag: monitoring
  timeout: 30
  endpoints:
    devices: /api/dcim/devices/
    virtual_machines: /api/virtualization/virtual-machines/
```

| Key | Type | Default | Description |
|---|---|---|---|
| `url` | string | *(required)* | Base URL of your NetBox instance (no trailing slash needed) |
| `tag` | string | `monitoring` | Slug of the tag used to filter devices and VMs. Set to empty string `""` to fetch all devices |
| `timeout` | int | `30` | HTTP request timeout in seconds |
| `endpoints` | dict | *(see below)* | Override API paths if your NetBox uses non-standard routes |

Default endpoints:

```yaml
endpoints:
  devices: /api/dcim/devices/
  virtual_machines: /api/virtualization/virtual-machines/
```

> The API token is **not** configured here. Set it via the `NETBOX_TOKEN` environment variable.

See [NetBox Setup](netbox-setup.md) for details on token creation, permissions, and custom fields.

---

## prometheus

Generates per-group YAML scrape config files for the SNMP exporter.

```yaml
prometheus:
  snmp_exporter_address: "snmp-exporter:9116"
  metrics_path: /snmp
  scrape_dir: /opt/configs/prometheus-scrape
  reload_address: "http://prometheus:9090"
  default_labels:
    instance: "{name}"
    criticality: "{criticality}"
  groups:
    # ... group definitions
```

| Key | Type | Default | Description |
|---|---|---|---|
| `snmp_exporter_address` | string | `localhost:9116` | Address of the snmp_exporter instance (used in relabel_configs) |
| `metrics_path` | string | `/snmp` | Metrics path for snmp_exporter |
| `scrape_dir` | string | `./prometheus_scrape` | Directory where per-group `.yml` files are written |
| `reload_address` | string | *(empty)* | Prometheus URL for `/-/reload` call after generation. Leave empty to skip reload |
| `default_labels` | dict | `{}` | Labels applied to every `static_config` target. Supports [placeholders](#placeholders) |
| `groups` | dict | `{}` | Group definitions (see [Prometheus group options](#prometheus-group-options)) |

**Output behavior:**

- One YAML file per group: `<scrape_dir>/<group_name>.yml`
- Each file contains a single `scrape_configs` entry with `job_name` = group name
- Groups with **zero** matching devices → output file is **deleted** (if it previously existed)
- After writing all files, the service calls `POST <reload_address>/-/reload` (if configured)

See [Receiver Setup → Prometheus](receivers-setup.md#1-prometheus-snmp-exporter) for the output file structure and receiver configuration.

---

## probe_icmp

Generates a single JSON file with ICMP targets for Grafana Alloy's blackbox exporter. Targets are derived from **devices and VMs** in NetBox.

```yaml
probe_icmp:
  targets_file: /etc/alloy/blackbox_targets.json
  default_labels:
    __param_module: icmp
    environment: prod
    request: icmp
    criticality: "{criticality}"
    name: "{name}"
  groups:
    # ... group definitions
```

| Key | Type | Default | Description |
|---|---|---|---|
| `targets_file` | string | `/etc/alloy/blackbox_targets.json` | Path to the output JSON file |
| `reload_address` | string | *(empty)* | Alloy URL for `/-/reload` call after generation. Leave empty to skip reload |
| `default_labels` | dict | `{}` | Labels applied to every target. Overridden by per-group `labels` |
| `groups` | dict | `{}` | Group definitions (see [probe_icmp group options](#probe_icmp-group-options)) |

**Output behavior:**

- A single JSON array of `{ targets, labels }` objects
- `default_labels` are merged with per-group `labels` (group takes precedence)
- Setting a label to `null` in a group **removes** it for that group's targets
- A device can appear in **multiple groups** unless an earlier group sets `exclusive: true`
- Groups are processed in **YAML insertion order** for each device

See [Receiver Setup → Alloy](receivers-setup.md#2-grafana-alloy-blackbox-icmp) for the output file structure and receiver configuration.

> **Backwards compatibility:** The config section name `alloy` is still accepted as an alias for `probe_icmp`. Similarly, `ENABLE_ALLOY=true` maps to the `probe_icmp` generator.

---

## probe_http

Generates a single JSON file with HTTP targets for Grafana Alloy's blackbox exporter. Targets are derived from **IPAM services** in NetBox that have the monitoring tag and a URL in a custom field.

```yaml
probe_http:
  targets_file: /etc/alloy/probe_http_targets.json
  website_field: website
  name_field: hostname
  default_labels:
    __param_module: http_2xx
    environment: prod
    request: http
    name: "{name}"
    service_name: "{name}"
  groups:
    # ... group definitions
```

| Key | Type | Default | Description |
|---|---|---|---|
| `targets_file` | string | `/etc/alloy/probe_http_targets.json` | Path to the output JSON file |
| `reload_address` | string | *(empty)* | Alloy URL for `/-/reload` call after generation. Leave empty to skip reload |
| `website_field` | string | `website` | Name of the custom field on IPAM services that holds the URL |
| `name_field` | string | `hostname` | How to derive the target name: `hostname` (from URL), `description`, `name`, or `device_name` |
| `default_labels` | dict | `{}` | Labels applied to every target. Overridden by per-group `labels` |
| `groups` | dict | `{}` | Group definitions (see [probe_http group options](#probe_http-group-options)) |

**Output behavior:**

- Fetches services from `/api/ipam/services/?tag=<tag>`, filters to those with a non-empty `website_field`
- A single JSON array of `{ targets, labels }` objects
- Each target's address is the URL from the custom field
- If no `groups` are defined, all services go into a single default group
- Conditions match against `Service` fields (see [Service fields](#service-fields-for-conditions))

See [Receiver Setup → Alloy HTTP](receivers-setup.md#3-grafana-alloy-blackbox-http) for the output file structure and receiver configuration.

### Service fields for conditions

The `probe_http` generator works with a `Service` model that has different fields than `Device`:

| Field | Source | Type |
|---|---|---|
| `name` | Service name | string |
| `protocol` | Service protocol (`tcp`, `udp`) | string or None |
| `description` | Service description | string or None |
| `website` | URL from custom field | string |
| `device_name` | Parent device/VM name | string or None |
| `tags` | Tag slugs | list[string] |

---

## syslog

Generates syslog-ng rewrite rules inside a single `rewrite` block. The output file is **fully managed** — generated from scratch on each run.

```yaml
syslog:
  config_file: /etc/syslog-ng/conf.d/netbox2prom.conf
  block_name: fix_hostnames
  control_socket: /var/lib/syslog-ng/syslog-ng.ctl
  epilogue_template: |-
        set("${{SOURCEIP}}", value("HOST")
            condition("${{HOST}}" eq ""));
  groups:
    # ... group definitions
```

| Key | Type | Default | Description |
|---|---|---|---|
| `config_file` | string | *(required)* | Path to the syslog-ng config file (fully managed, created if not exists) |
| `block_name` | string | `fix_hostnames` | Name of the `rewrite` block in the generated file |
| `control_socket` | string | `/var/lib/syslog-ng/syslog-ng.ctl` | Path to the syslog-ng control socket for `syslog-ng-ctl reload` |
| `syntax_check` | bool | `true` | Validate generated config with `syslog-ng --syntax-only` before applying. Skips gracefully if binary not found |
| `health_check_delay` | int | `3` | Seconds to wait after reload before checking syslog-ng status |
| `epilogue_template` | string | *(empty)* | Rules appended after all group rules. Uses double-brace escaping for syslog-ng macros |
| `groups` | dict | `{}` | Group definitions (see [Syslog group options](#syslog-group-options)) |

**Output behavior:**

- The file at `config_file` is **generated from scratch** on each run (not modified in-place).
- If content is unchanged → **no write, no reload** (no-op).
- If content changed → file is written **atomically** (temp file + rename), then syslog-ng is **reloaded** via `syslog-ng-ctl reload`.
- After reload, syslog-ng status is checked. If not running → **rollback** to previous config (`.bak`).
- If no devices match any group → file is **removed** (if it existed) and syslog-ng is reloaded.

See [Receiver Setup → syslog-ng](receivers-setup.md#3-syslog-ng-hostname-rewrites) for details.

---

## Conditions

Conditions are declarative matching rules. Each key in a `conditions` dict maps a **device field** to a **match criterion**. All conditions must be satisfied (logical AND).

Available device fields for matching:

| Field | Source | Type |
|---|---|---|
| `name` | Device name | string |
| `main_ip` | Primary IP4/IP | string or None |
| `oob_ip` | Out-of-band IP | string or None |
| `os_type` | `config_context.os` | string or None |
| `vendor` | `manufacturer.slug` | string or None |
| `model` | `device_type.slug` (lowercased) | string or None |
| `role` | `role.slug` | string or None |
| `snmp_ver` | `custom_fields.snmp_ver` | int (default `0`) |
| `snmp_cipher` | `custom_fields.snmp_cipher` | string or None |
| `criticality` | `custom_fields.criticality` | string or None |
| `virtual` | Derived from VM endpoint | bool |

---

### Exact match

Matches when the device field equals the specified value (string comparison).

```yaml
conditions:
  vendor: dell          # manufacturer slug is exactly "dell"
  role: ups             # role slug is exactly "ups"
```

Comparison is **case-sensitive** string equality (`str(val) == str(cond)`). The exception is `model`, which is case-insensitive (see [Normalization](#condition-normalization)).

---

### List match

Matches when the device field's value is **one of** the listed values.

```yaml
conditions:
  role: [switch, router]          # role is "switch" OR "router"
  vendor: [huawei, hpe]           # vendor is "huawei" OR "hpe"
  model: [S215Gi-8T-POE]          # model is this specific model (case-insensitive)
```

Each value is compared as a string. The `model` field is lowercased before comparison (see [Normalization](#condition-normalization)).

---

### not_null

Matches when the field has a value (is not `None`).

```yaml
conditions:
  main_ip: not_null     # device has a primary IP address
  oob_ip: not_null      # device has an out-of-band IP address
  os_type: not_null     # device has OS info from config context
```

This is useful for filtering devices that have a specific address configured. Empty strings are treated as **valid** (not null) — only Python `None` fails this check. In practice, NetBox returns `None` for unset fields.

---

### null

Matches when the field is **empty** (has no value).

```yaml
conditions:
  oob_ip: null          # device has NO out-of-band IP
  os_type: null         # device has NO OS info in config context
```

The opposite of `not_null`. Use this to route devices that are missing a field into a different group (e.g., devices without OS info go to the "no Alloy agent" ICMP group).

---

### any_except

Matches when the field **has a value** AND that value is **not in** the exclude list. Requires a companion `<field>_exclude` key.

```yaml
conditions:
  vendor: any_except
  vendor_exclude: [dell, hpe, gigabyte]   # any vendor EXCEPT these three

  role: any_except
  role_exclude: [switch, ups, router]      # any role EXCEPT these

  snmp_ver: any_except
  snmp_ver_exclude: [0]                    # any SNMP version except 0 (i.e., SNMP is configured)
```

**Semantics:**

1. If the field is `None` → **no match** (the field must be populated).
2. If the field's value is in the exclude list → **no match**.
3. Otherwise → **match**.

The exclude list is specified as `<field_name>_exclude`:

```yaml
conditions:
  <field>: any_except
  <field>_exclude: [value1, value2, ...]
```

This is the most common condition for "catch-all" groups — e.g., matching all vendors that don't have a dedicated group.

---

### not_in

Matches when the field is either `None` **or** not in the exclude list. Requires a companion `<field>_exclude` key.

```yaml
conditions:
  vendor: not_in
  vendor_exclude: [synology]               # vendor is not synology (or vendor is unset)

  role: not_in
  role_exclude: [switch, ups, router]      # role is not one of these (or role is unset)

  model: not_in
  model_exclude: [generic-ws]              # model is not generic-ws (or model is unset)
```

**Semantics:**

1. If the field is `None` → **match** (empty fields pass — this is the key difference from `any_except`).
2. If the field's value is in the exclude list → **no match**.
3. Otherwise → **match**.

| | `any_except` | `not_in` |
|---|---|---|
| Field is `None` | No match | **Match** |
| Field in exclude list | No match | No match |
| Field set, not in list | Match | Match |

> Use `any_except` when the field **must** be populated. Use `not_in` when an empty field is acceptable.

---

### tags_contains

Matches when the device has **at least one** of the specified tags.

```yaml
conditions:
  tags_contains: [management]          # device has the "management" tag
  tags_contains: [linux, windows]      # device has "linux" OR "windows" tag
```

Can also accept a single string (treated as a one-element list):

```yaml
conditions:
  tags_contains: management
```

Tags are compared by **slug** (not display name). This is a special condition type — it doesn't use the standard field matching logic.

---

### Numeric match

Numeric fields are compared as strings after conversion. The `snmp_ver` field (type `int`) is the most common case:

```yaml
conditions:
  snmp_ver: 3          # SNMPv3
  snmp_ver: 2          # SNMPv2c
  snmp_ver: 1          # SNMPv1
  snmp_ver: 0          # no SNMP configured
```

Internally, the value is converted via `str(val)` before comparison, so `3` (int) matches `"3"` (string in YAML). You can write either form in your config — YAML `3` and `"3"` both work.

---

### Boolean match

The `virtual` field is a boolean. Comparison is string-based after conversion:

```yaml
conditions:
  virtual: false       # physical device (str(False) == "false")
  virtual: true        # virtual machine
```

> In YAML, `false` is parsed as a boolean. The condition value is converted to a string and compared against `str(device.virtual)`. Make sure to use lowercase `true`/`false` in the config — `True`/`False` (capitalized) would produce `"True"` which won't match.

---

### Condition normalization

Most fields are compared **case-sensitively** as strings. The exception is `model`:

| Field | Comparison | Lowercased? | Example |
|---|---|---|---|
| `model` | Case-insensitive | Yes — both the device value and condition/list values are lowercased | `S215Gi-8T-POE` → `s215gi-8t-poe` |
| All others | Case-sensitive | No | `dell` matches `dell`, not `Dell` |

The `model` field is automatically lowercased from `device_type.slug` during device parsing. When writing conditions, use lowercase values:

```yaml
# Correct — values will be lowercased before comparison
conditions:
  model: [S215Gi-8T-POE]          # OK, becomes s215gi-8t-poe
  model_exclude: [generic-ws]     # OK, already lowercase

# Also correct in any_except/not_in
conditions:
  model: not_in
  model_exclude: [Generic-WS]     # OK, becomes generic-ws
```

> The lowercasing applies to `model` conditions regardless of the match type (exact, list, `any_except`, `not_in`). Other fields like `vendor`, `role` are compared as-is.

---

### Multi-field exclude lists

The `<field>_exclude` key is tied to its parent field by name convention. Each field that uses `any_except` or `not_in` needs its own exclude list:

```yaml
conditions:
  vendor: any_except
  vendor_exclude: [dell, hpe, gigabyte]     # applies to "vendor" only

  role: not_in
  role_exclude: [switch, ups, router]        # applies to "role" only

  snmp_ver: any_except
  snmp_ver_exclude: [0]                       # applies to "snmp_ver" only

  model: not_in
  model_exclude: [generic-ws]                 # applies to "model" only
```

> The exclude key is always `<field>_exclude`. The `_exclude` suffix keys are skipped during condition iteration and are only read when the corresponding field uses `any_except` or `not_in`.

---

### Combining conditions

All conditions in a group are combined with **logical AND** — every condition must pass for a device to match the group.

```yaml
conditions:
  vendor: dell                    # AND
  oob_ip: not_null                # AND
  snmp_ver: 3                     # AND
  virtual: false                  # AND
  role: any_except                # AND
  role_exclude: [switch, ups, router]
```

This matches: Dell physical devices with an OOB IP, SNMPv3 configured, and a role that is not switch/ups/router.

There is no OR between conditions within a single group. To express OR, create **separate groups** (e.g., one group for SNMPv2, another for SNMPv3).

---

### Conditions quick reference

| Criterion | Syntax | Requires companion key | Empty field passes? |
|---|---|---|---|
| `"value"` | Exact string match | No | No |
| `[a, b]` | Value in list | No | No |
| `not_null` | Field is populated | No | — (this IS the check) |
| `null` | Field is empty | No | — (this IS the check) |
| `any_except` | Populated AND not in exclude list | `<field>_exclude: [...]` | No (must be populated) |
| `not_in` | Empty OR not in exclude list | `<field>_exclude: [...]` | Yes |
| `tags_contains: [...]` | Has at least one tag | No | N/A |
| `3` (number) | Exact match (compared as string) | No | No |
| `true` / `false` | Boolean match (compared as string) | No | No |

---

## Placeholders

Placeholders can be used in `default_labels` (prometheus, probe_icmp & probe_http), `labels` (probe_icmp/probe_http groups), and `template` (syslog groups). They are resolved per-device (or per-service for probe_http) at generation time.

| Placeholder | Value | Generator | Example |
|---|---|---|---|
| `{name}` | Device name with `name_prefix`/`name_suffix` applied (probe_icmp) or resolved service name (probe_http) | all | `srv-web-01` |
| `{target_ip}` | IP from the `target_field` (probe_icmp) or `ip_field` (Prometheus) | prometheus, probe_icmp | `10.10.10.5` |
| `{website}` | URL from the service custom field | probe_http | `https://wiki.example.com` |
| `{description}` | Service description | probe_http | `Wiki` |
| `{device_name}` | Parent device/VM name of the service | probe_http | `oxt-vs-wiki01` |
| `{protocol}` | Service protocol (tcp/udp) | probe_http | `tcp` |
| `{device_label}` | `"virtual"` for VMs, `"device"` for physical | prometheus, probe_icmp | `device` |
| `{criticality}` | Value of `custom_fields.criticality` | prometheus, probe_icmp | `high` |
| `{os_type}` | Value of `config_context.os` | prometheus, probe_icmp | `linux` |
| `{os}` | Alias for `{os_type}` | prometheus, probe_icmp | `linux` |
| `{main_ip}` | Primary IP address | prometheus, probe_icmp | `10.10.10.5` |
| `{oob_ip}` | Out-of-band IP address | prometheus, probe_icmp | `192.168.1.50` |
| `{vendor}` | Manufacturer slug | prometheus, probe_icmp | `dell` |
| `{model}` | Device type slug (lowercased) | prometheus, probe_icmp | `poweredge-r650` |
| `{role}` | Role slug | prometheus, probe_icmp | `server` |
| `{snmp_ver}` | SNMP version as string | prometheus, probe_icmp | `3` |

**Empty values:** If a field is `None`, the placeholder resolves to an **empty string** (`""`), not the literal placeholder text. This prevents `{criticality}` from appearing in output labels when the field is unset.

**Usage examples:**

```yaml
# Prometheus default_labels
default_labels:
  instance: "{name}"
  criticality: "{criticality}"

# Alloy group labels
labels:
  os: "{os_type}"
  node_ip: "{target_ip}"
  device: "{device_label}"

# Syslog template (uses {name} and {ip}, not {target_ip})
template: |-
    set("{name}", value("PROGRAM") \
        condition("${{HOST}}" eq "{ip}"));
```

> In syslog templates, `{name}` is cleaned (whitespace trimmed, `"` escaped to `\"`) before substitution. `{ip}` is the value from `host_field`. Syslog-ng macros use double braces: `${{HOST}}` → `${HOST}`.

---

## probe_icmp group options

Each group under `probe_icmp.groups` supports the following keys:

```yaml
probe_icmp:
  groups:
    my_group_name:                    # becomes the group identifier (used in logs)
      conditions: { ... }             # matching rules (see Conditions)
      target_field: main_ip           # device field to use as the target IP
      exclusive: true                 # skip remaining groups for this device
      name_prefix: "prefix-"          # prepend to device name
      name_suffix: "-suffix"          # append to device name
      labels:                         # per-group labels (override default_labels)
        device: switch
        snmp: "true"
        node_ip: "{target_ip}"
```

| Key | Type | Default | Description |
|---|---|---|---|
| `conditions` | dict | `{}` | Matching conditions. Empty dict = matches all devices |
| `target_field` | string | `main_ip` | Device field for the target IP. Usually `main_ip` or `oob_ip` |
| `exclusive` | bool | `false` | If `true`, no subsequent groups are evaluated for this device. Allows first-match-wins routing |
| `name_prefix` | string | `""` | Prepended to device name (affects `{name}` placeholder) |
| `name_suffix` | string | `""` | Appended to device name (affects `{name}` placeholder) |
| `labels` | dict | `{}` | Labels merged on top of `default_labels`. Set to `null` to remove a default label |

### How `exclusive` works

Groups are evaluated in **YAML insertion order** for each device. When a device matches a group with `exclusive: true`, the device is added to that group and **skipped** for all remaining groups:

```yaml
groups:
  # Evaluated first — if matched, device skips all other groups
  management_icmp:
    exclusive: true
    conditions:
      tags_contains: [management]
    target_field: main_ip
    labels:
      device: management

  # Only reached if management_icmp didn't match
  linux_servers:
    conditions:
      os_type: not_null
    target_field: main_ip
    labels:
      device: "{device_label}"
```

Without `exclusive`, a device can appear in multiple groups — which is often desired (e.g., a switch appears in both `switch_snmp` and `switch_no_snmp` is prevented by mutually exclusive conditions, not by the `exclusive` flag).

### Label resolution order

For each target, labels are resolved in this order (later overrides earlier):

1. `default_labels` from the `probe_icmp` section
2. `labels` from the matched group
3. Any label set to `null` in the group's `labels` → **removed** from the final set

Then all label values are resolved through [placeholders](#placeholders).

---

## probe_http group options

Each group under `probe_http.groups` supports the following keys:

```yaml
probe_http:
  groups:
    my_group_name:                    # used in logs
      conditions: { ... }             # matching rules against Service fields
      exclusive: true                 # skip remaining groups for this service
      labels:                         # per-group labels (override default_labels)
        __param_module: http_2xx_strict
        device: api
```

| Key | Type | Default | Description |
|---|---|---|---|
| `conditions` | dict | `{}` | Matching conditions against [Service fields](#service-fields-for-conditions). Empty dict = matches all services |
| `exclusive` | bool | `false` | If `true`, no subsequent groups are evaluated for this service |
| `labels` | dict | `{}` | Labels merged on top of `default_labels`. Set to `null` to remove a default label |

> Unlike `probe_icmp`, the `probe_http` generator does not use `target_field` (the target is always the URL from the `website` custom field) or `name_prefix`/`name_suffix` (the name is derived via `name_field`).

### Example: multiple modules by tag

```yaml
probe_http:
  groups:
    # Regular websites — basic 2xx check
    websites:
      conditions: {}
      labels:
        __param_module: http_2xx

    # APIs with stricter validation
    api_endpoints:
      conditions:
        tags_contains: [api]
      labels:
        __param_module: http_2xx_strict
```

---

## Prometheus group options

Each group under `prometheus.groups` supports the following keys:

```yaml
prometheus:
  groups:
    my_job_name:                      # becomes job_name in the output YAML
      conditions: { ... }             # matching rules (see Conditions)
      ip_field: main_ip               # device field to use as the target IP
      scrape_interval: 4m             # Prometheus scrape interval
      scrape_timeout: 2m              # Prometheus scrape timeout
      params: { ... }                 # passed to snmp_exporter (auth, module)
      device_type: network            # sets device_type label via relabel
      vendor: huawei                  # sets vendor label via relabel
      relabel_configs: [ ... ]        # additional custom relabel_configs
```

| Key | Type | Default | Description |
|---|---|---|---|
| `conditions` | dict | `{}` | Matching conditions |
| `ip_field` | string | `oob_ip` | Device field for the target IP. Usually `main_ip` or `oob_ip` |
| `scrape_interval` | string | `5m` | Prometheus scrape interval |
| `scrape_timeout` | string | `4m` | Prometheus scrape timeout |
| `params` | dict | `{}` | Query parameters passed to snmp_exporter. Typically `auth` and `module` |
| `device_type` | string | *(optional)* | If set, adds a relabel rule setting the `device_type` label |
| `vendor` | string | *(optional)* | If set, adds a relabel rule setting the `vendor` label |
| `relabel_configs` | list | `[]` | Additional custom relabel_configs appended after the built-in ones |

### Built-in relabel_configs

Every group automatically gets these relabel rules (in order):

```yaml
relabel_configs:
  # 1. Copy target IP into __param_target for snmp_exporter
  - source_labels: [__address__]
    target_label: __param_target
    action: replace

  # 2. Rewrite __address__ to point at snmp_exporter
  - target_label: __address__
    replacement: snmp-exporter:9116
    action: replace

  # 3. Preserve original IP as node_ip label
  - source_labels: [__param_target]
    target_label: node_ip
    action: replace

  # 4. (if device_type is set) Set device_type label
  - target_label: device_type
    replacement: network
    action: replace

  # 5. (if vendor is set) Set vendor label
  - target_label: vendor
    replacement: huawei
    action: replace

  # 6. Custom relabel_configs from group config (appended last)
```

### params

The `params` dict maps directly to the `params` section of a Prometheus scrape config. snmp_exporter expects:

```yaml
params:
  auth:                   # auth profile name from snmp.yml
    - public_v3_network_auth_aes
  module:                 # module name(s) from snmp.yml (walked in order)
    - system
    - ip_mib
    - huawei
```

> The values must be **lists**, even for a single item. The generator passes them through verbatim to the output YAML.

---

## Syslog group options

Each group under `syslog.groups` supports the following keys:

```yaml
syslog:
  groups:
    my_group_name:                    # used in logs only
      conditions: { ... }             # matching rules (see Conditions)
      host_field: main_ip             # device field for the IP used in template
      template: |-                    # syslog-ng rule template (instantiated per device)
            set("{name}", value("PROGRAM") \
                condition("${{HOST}}" eq "{ip}"));
```

| Key | Type | Default | Description |
|---|---|---|---|
| `conditions` | dict | `{}` | Matching conditions |
| `host_field` | string | `main_ip` | Device field providing the IP for `{ip}` placeholder. Usually `main_ip` or `oob_ip` |
| `template` | string | *(required)* | syslog-ng rule, instantiated per matching device. Supports `{name}` and `{ip}` placeholders. Use `${{MACRO}}` for literal syslog-ng macros |

### Template details

- `{name}` — device name with whitespace trimmed and `"` escaped to `\"`
- `{ip}` — value from `host_field`
- `${{...}}` — double braces produce literal `{...}` in output for syslog-ng macros (e.g., `${{HOST}}` → `${HOST}`)

Indentation in the template is preserved as-is in the output. Use consistent indentation (typically 8 spaces or a tab) to match your syslog-ng config style.

### Epilogue

The `epilogue_template` is appended **once** after all group rules, **not** per-device. It is instantiated with `.format()` but receives no device context — only the double-brace escaping applies:

```yaml
epilogue_template: |-
      set("${{SOURCEIP}}", value("HOST")
          condition("${{HOST}}" eq ""));
```

Output:

```syslog-ng
set("${SOURCEIP}", value("HOST")
    condition("${HOST}" eq ""));
```

---

## Next Steps

- [NetBox Setup](netbox-setup.md) — required custom fields, tags, and config contexts
- [Receiver Setup](receivers-setup.md) — configure Prometheus, Alloy, and syslog-ng
- [`config.example.yml`](../config.example.yml) — fully annotated example configuration
