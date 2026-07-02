# NetBox Setup

This guide covers everything you need to configure on the **NetBox side** so that `netbox2prom` can read device data correctly.

---

## Table of Contents

- [1. API Token](#1-api-token)
- [2. Custom Fields](#2-custom-fields)
- [3. Config Contexts](#3-config-contexts)
- [4. Tags](#4-tags)
- [5. Device Fields Read by the Service](#5-device-fields-read-by-the-service)
- [5a. Service Fields Read by the Service](#5a-service-fields-read-by-the-service)
- [6. API Endpoints & Filtering](#6-api-endpoints--filtering)

---

## 1. API Token

`netbox2prom` authenticates to NetBox via an API token. The token is **never** stored in the config file — it is passed exclusively through the `NETBOX_TOKEN` environment variable.

### Creating a read-only token

1. Log in to NetBox as an administrator (or a user with appropriate permissions).
2. Navigate to **Admin → Users → API Tokens** (or click your profile → **API Tokens**).
3. Click **Add** and configure:
   - **User**: the service account or your user.
   - **Key**: leave blank to auto-generate.
   - **Write enabled**: **unchecked** (read-only is sufficient).
   - **Expires**: optional.
4. Save and copy the generated token.

### Required permissions

The token's user must have **read** access to:

| App | Model | Permission |
|---|---|---|
| DCIM | Device | `view` |
| Virtualization | Virtual Machine | `view` |
| IPAM | Service | `view` |
| Extras | Tag | `view` (inherited by default) |

If you restrict by object-level permissions, ensure the user can see all devices/VMs/services tagged with your monitoring tag.

### Passing the token

```bash
export NETBOX_TOKEN="0123456789abcdef0123456789abcdef01234567"
```

Or in `docker-compose.yml`:

```yaml
environment:
  NETBOX_TOKEN: ${NETBOX_TOKEN}
```

---

## 2. Custom Fields

`netbox2prom` reads three custom fields from **DCIM → Device**. You need to create them in NetBox under **Admin → Customization → Custom Fields** (NetBox 3.5+) or **Admin → Extras → Custom Fields** (older versions).

### `snmp_ver`

The SNMP version configured on the device. This field controls which scrape groups and auth profiles the device lands in.

| Property | Value |
|---|---|
| **Type** | Integer |
| **Object type** | `dcim > device` (and `virtualization > virtual machine` if needed) |
| **Label** | `SNMP Version` |
| **Default value** | `0` |
| **Description** | `0 = no SNMP, 1 = SNMPv1, 2 = SNMPv2c, 3 = SNMPv3` |

> The default of `0` means "no SNMP monitoring." Devices with `snmp_ver: 0` will be skipped by Prometheus groups that require SNMP, but can still appear in Alloy ICMP checks.

### `snmp_cipher`

The SNMPv3 encryption cipher. Only relevant when `snmp_ver = 3`.

| Property | Value |
|---|---|
| **Type** | Selection |
| **Object type** | `dcim > device` |
| **Label** | `SNMPv3 Cipher` |
| **Choices** | `aes`, `des` |
| **Default value** | *(none)* |

> This field lets you split SNMPv3 devices into separate scrape groups with different auth profiles (e.g., AES vs DES), since some hardware only supports older ciphers.

### `criticality`

A free-form criticality label that is propagated as a Prometheus/Alloy label, useful for alerting routing and dashboards.

| Property | Value |
|---|---|
| **Type** | Selection **or** Text |
| **Object type** | `dcim > device`, `virtualization > virtual machine` |
| **Label** | `Criticality` |
| **Choices** *(if Selection)* | your own, e.g. `high`, `medium`, `low` |

> Whatever type you choose, the value is stored as a string and available via the `{criticality}` placeholder.

### `website` (IPAM Service)

Used by the `probe_http` generator to determine which services to monitor via HTTP blackbox checks. Only services with this field populated are included in `probe_http`. Services **without** this field are eligible for `probe_tcp` (TCP port checks) if they have a TCP protocol, ports, and IP addresses configured.

| Property | Value |
|---|---|
| **Type** | Text |
| **Object type** | `ipam > service` |
| **Label** | `Сайт` *(or `Website`)* |
| **Description** | Full URL for the website (only for web services). Specify the full path |
| **Validation regex** | `^(https?:\/\/)[a-zA-Z0-9.\-_]+(\/[a-zA-Z0-9.\-_]*)*$` |
| **Default** | *(none)* |

> Example values: `https://wiki.example.com`, `https://redmine.example.com/login?back_url=...`

To use a different custom field name, set `website_field` in the `probe_http` config section.

> **probe_http vs probe_tcp:** Services with a populated `website` field are handled by `probe_http` (HTTP checks on the URL). Services without `website` but with protocol `tcp`, ports, and IP addresses are handled by `probe_tcp` (TCP port checks on `ip:port`). This split is automatic — no additional configuration is needed beyond the `monitoring` tag.

---

## 3. Config Contexts

`netbox2prom` reads the `os` key from each device's **config context** to populate the `os_type` field. This is used to:

- Determine whether a server has an Alloy agent installed (via `os_type: not_null` condition in Alloy groups).
- Propagate the OS as a label via the `{os_type}` / `{os}` placeholder.

### Setup

1. Navigate to **Admin → Customization → Config Contexts**.
2. Create a context for each platform you want to tag. For example:

**Linux servers:**

| Property | Value |
|---|---|
| **Name** | `OS - Linux` |
| **Weight** | `1000` |
| **Data** | `{"os": "linux"}` |
| **Assignment** | Tag: `linux` (or platform, cluster, site — whatever fits your setup) |

**Windows servers:**

| Property | Value |
|---|---|
| **Name** | `OS - Windows` |
| **Weight** | `1000` |
| **Data** | `{"os": "windows"}` |
| **Assignment** | Tag: `windows` (or platform) |

> Devices **without** a matching config context will have `os_type = None`. This is intentional — the `os_type: null` condition in Alloy groups routes them to the "no Alloy agent" ICMP-only group.

### How it works

The service reads `config_context.os` from the NetBox API response. Only the `os` key is used; other config context keys are ignored.

```python
# See: src/netbox2prom/models.py
os_type=config_context.get("os"),
```

---

## 4. Tags

Tags control which devices `netbox2prom` processes and enable special routing in Alloy rules.

### `monitoring` tag (required)

This is the primary filter. Only devices, VMs, and IPAM services with this tag are fetched from NetBox.

| Property | Value |
|---|---|
| **Name** | `Monitoring` |
| **Slug** | `monitoring` |
| **Object types** | `dcim > device`, `virtualization > virtual machine`, `ipam > service` |

The tag name is configurable:

```yaml
netbox:
  tag: monitoring   # change to any slug you prefer
```

> If `tag` is omitted or empty, **all** devices, VMs, and services are fetched (use with caution on large installations).

### `management` tag (optional)

Used in Alloy group conditions to route management interfaces to a dedicated target group. This is **not** required by the service itself — it only matters if your `config.yml` references it:

```yaml
alloy:
  groups:
    management_icmp:
      conditions:
        tags_contains: [management]   # devices with this tag
```

Create it in NetBox with slug `management` if you use this rule.

### Assigning tags

Any combination of tags works. A typical server might have `monitoring` + `linux`; a switch might have `monitoring` only.

---

## 5. Device Fields Read by the Service

`netbox2prom` maps the following NetBox API fields to internal `Device` attributes. Understanding this mapping helps you configure conditions and placeholders correctly.

| NetBox API field | Internal field | Type | Notes |
|---|---|---|---|
| `name` | `name` | string | Device hostname |
| `primary_ip4.address` or `primary_ip.address` | `main_ip` | string | IP without prefix (e.g. `10.0.0.1`) |
| `oob_ip.address` | `oob_ip` | string | Out-of-band IP without prefix |
| `config_context.os` | `os_type` | string | From config context |
| `device_type.manufacturer.slug` | `vendor` | string | Lowercase slug |
| `device_type.slug` | `model` | string | **Lowercased** automatically |
| `role.slug` | `role` | string | Device role slug |
| `custom_fields.snmp_ver` | `snmp_ver` | int | Default `0` |
| `custom_fields.snmp_cipher` | `snmp_cipher` | string | `aes` / `des` / `None` |
| `custom_fields.criticality` | `criticality` | string | Your values |
| *(derived)* | `virtual` | bool | `True` for VMs, `False` for physical devices |
| `tags[].slug` | `tags` | list[string] | Tag slugs |

> **Note on `virtual`**: The service detects virtual machines by checking for the presence of a `vcpus` key in the API response — this is a VM-specific field from the `/api/virtualization/virtual-machines/` endpoint. Physical devices always have `virtual = False`.

> **Note on `model`**: The `device_type.slug` is lowercased during normalization. When you write conditions involving `model`, use lowercase values (e.g. `s215gi-8t-poe`, not `S215Gi-8T-POE`). See [Configuration → Condition normalization](configuration.md#condition-normalization).

> **Note on IP resolution**: `primary_ip4` is checked first; if absent, `primary_ip` (which may be IPv6) is used. The `/prefix` part is stripped automatically.

---

## 5a. Service Fields Read by the Service

The `probe_http` and `probe_tcp` generators work with **IPAM services**. The service maps the following NetBox API fields to internal `Service` attributes:

| NetBox API field | Internal field | Type | Notes |
|---|---|---|---|
| `name` | `name` | string | Service name (e.g., `SSH`, `HTTPS`) |
| `protocol.value` | `protocol` | string | `tcp` or `udp` |
| `description` | `description` | string | Service description |
| `custom_fields.<website_field>` | `website` | string | URL from custom field (default field name: `website`) |
| `device.name` or `virtual_machine.name` | `device_name` | string | Parent device or VM name |
| `ports` | `ports` | list[int] | Port numbers (e.g., `[22]`, `[80, 443]`) |
| `ipaddresses[].address` | `ipaddresses` | list[string] | IPs without CIDR prefix (e.g., `10.15.5.7` from `10.15.5.7/24`) |
| `tags[].slug` | `tags` | list[string] | Tag slugs |

> **IP address resolution**: The `ipaddresses` list is built from the service's assigned IP addresses. The CIDR prefix (`/24`, `/32`, etc.) is stripped automatically. For `probe_tcp`, the **first** IP in the list is used as the target.

> **Required permissions**: The token's user must have **read** access to `IPAM > Service` (`view`). This is in addition to the DCIM and Virtualization permissions listed in [Section 1](#1-api-token).

---

## 6. API Endpoints & Filtering

### Default endpoints

The service polls three endpoints:

| Endpoint | Purpose | Used by |
|---|---|---|
| `/api/dcim/devices/` | Physical devices | prometheus, probe_icmp, syslog |
| `/api/virtualization/virtual-machines/` | Virtual machines | prometheus, probe_icmp, syslog |
| `/api/ipam/services/` | IPAM services | probe_http, probe_tcp |

### Tag filtering

All endpoints are queried with `?tag=<your_tag>`:

```
GET /api/dcim/devices/?tag=monitoring
GET /api/virtualization/virtual-machines/?tag=monitoring
GET /api/ipam/services/?tag=monitoring
```

All matching devices, VMs, and services are fetched and processed by the relevant enabled generators.

### Custom endpoints

If your NetBox deployment uses non-standard API paths (e.g., behind a reverse proxy with a prefix), override them:

```yaml
netbox:
  url: "https://netbox.example.com"
  endpoints:
    devices: /api/dcim/devices/
    virtual_machines: /api/virtualization/virtual-machines/
    services: /api/ipam/services/
```

### Timeout

The default API request timeout is 30 seconds. Adjust if your NetBox is slow or has a large inventory:

```yaml
netbox:
  timeout: 60
```

### Pagination

The client follows pagination automatically — all pages are fetched and combined. No configuration needed.

---

## Next Steps

- [Configuration Reference](configuration.md) — how to write matching rules and output configs
- [Receiver Setup](receivers-setup.md) — configure Prometheus, Alloy, and Syslog-ng to consume the generated files
