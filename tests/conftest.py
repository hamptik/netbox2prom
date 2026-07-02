"""Shared pytest fixtures and hand-written fakes.

Following the pattern from netbox2mapgl: no mocking library is used.
Instead, lightweight stub classes are swapped in via attribute assignment.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from netbox2prom.models import Device, Service

# ---------------------------------------------------------------------------
# HTTP fakes (for NetBoxClient and reload tests)
# ---------------------------------------------------------------------------


class FakeResponse:
    """Mimics requests.Response with a pre-set JSON payload."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Mimics requests.Session.get using a scripted list of payloads.

    Records every call so tests can assert on URLs and query params.
    """

    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        self.calls.append((url, dict(params or {})))
        return FakeResponse(self._pages.pop(0))


class FakePostResponse:
    """Mimics requests.post response."""

    def __init__(self, status: int = 200) -> None:
        self.status_code = status


# ---------------------------------------------------------------------------
# Device / Service builders
# ---------------------------------------------------------------------------


def make_device(
    *,
    name: str = "router1",
    main_ip: str | None = "10.0.0.1",
    oob_ip: str | None = "192.168.0.1",
    os_type: str | None = "linux",
    vendor: str | None = "cisco",
    model: str | None = "catalyst-9300",
    role: str | None = "router",
    snmp_ver: int = 2,
    criticality: str | None = "high",
    virtual: bool = False,
    tags: list[str] | None = None,
) -> Device:
    return Device(
        name=name,
        main_ip=main_ip,
        oob_ip=oob_ip,
        os_type=os_type,
        vendor=vendor,
        model=model,
        role=role,
        snmp_ver=snmp_ver,
        criticality=criticality,
        virtual=virtual,
        tags=tags or [],
    )


def make_service(
    *,
    name: str | None = "web",
    protocol: str | None = "tcp",
    description: str | None = "Web service",
    website: str | None = "https://example.com",
    device_name: str | None = "server1",
    tags: list[str] | None = None,
) -> Service:
    return Service(
        name=name,
        protocol=protocol,
        description=description,
        website=website,
        device_name=device_name,
        tags=tags or [],
    )


def nb_device(
    *,
    name: str = "router1",
    manufacturer_slug: str = "cisco",
    type_slug: str = "catalyst-9300",
    role_slug: str = "router",
    primary_ip: str | None = "10.0.0.1/24",
    primary_ip4: str | None = None,
    oob_ip: str | None = "192.168.0.1/24",
    os: str | None = "iosxe",
    custom_fields: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    vcpus: int | None = None,
) -> dict[str, Any]:
    """Build a NetBox API device JSON payload."""
    data: dict[str, Any] = {
        "name": name,
        "device_type": {
            "slug": type_slug,
            "manufacturer": {"slug": manufacturer_slug},
        },
        "role": {"slug": role_slug},
        "config_context": {"os": os} if os else {},
        "custom_fields": custom_fields or {},
        "tags": [{"slug": t} for t in (tags or [])],
    }
    if primary_ip4:
        data["primary_ip4"] = {"address": primary_ip4}
    elif primary_ip:
        data["primary_ip"] = {"address": primary_ip}
    if oob_ip:
        data["oob_ip"] = {"address": oob_ip}
    if vcpus is not None:
        data["vcpus"] = vcpus
    return data


def nb_service(
    *,
    name: str = "web",
    protocol: dict[str, str] | str | None = None,
    description: str | None = "Web service",
    website: str | None = "https://example.com",
    device_name: str | None = "server1",
    vm_name: str | None = None,
    tags: list[str] | None = None,
    website_field: str = "website",
    protocol_missing: bool = False,
) -> dict[str, Any]:
    """Build a NetBox IPAM service JSON payload.

    Set protocol_missing=True to omit the protocol key entirely.
    """
    if protocol_missing:
        proto: Any = None
    else:
        proto = protocol if protocol is not None else {"label": "TCP", "value": "tcp"}
    data: dict[str, Any] = {
        "name": name,
        "description": description,
        "custom_fields": {},
        "tags": [{"slug": t} for t in (tags or [])],
    }
    if proto is not None:
        data["protocol"] = proto
    if website is not None:
        data["custom_fields"][website_field] = website
    if device_name:
        data["device"] = {"name": device_name}
    if vm_name:
        data["virtual_machine"] = {"name": vm_name}
    return data


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ENABLE_* and runtime env vars that could leak between tests."""
    for key in [
        "NETBOX_TOKEN",
        "NETBOX_PAGE_SIZE",
        "ENABLE_PROMETHEUS",
        "ENABLE_PROBE_ICMP",
        "ENABLE_ALLOY",
        "ENABLE_PROBE_HTTP",
        "ENABLE_SYSLOG",
        "RUN_ONCE",
        "POLL_INTERVAL",
        "LOG_LEVEL",
        "NETBOX2PROM_CONFIG",
    ]:
        monkeypatch.delenv(key, raising=False)
