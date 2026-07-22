from __future__ import annotations

import json
from pathlib import Path

from netbox2prom.models import (
    Device,
    IpAddress,
    Service,
    _extract_service_parent_name,
    enrich_ip_address,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Device.from_netbox
# ---------------------------------------------------------------------------

def test_device_physical_parses_all_fields():
    d = Device.from_netbox(load("device_physical.json"))
    assert d.id == 1001
    assert d.name == "device-01"
    assert d.main_ip == "192.0.2.10"
    assert d.oob_ip == "192.0.2.11"
    assert d.vendor == "acme"
    assert d.model == "tower-100"
    assert d.role == "server"
    assert d.os_type == "linux"
    assert d.snmp_ver == 3
    assert d.snmp_cipher == "aes"
    assert d.criticality == 3
    assert d.virtual is False
    assert d.tags == ["monitoring"]


def test_device_virtual_detected_by_vcpus_field():
    d = Device.from_netbox(load("device_virtual.json"))
    assert d.virtual is True
    assert d.oob_ip is None
    assert d.main_ip == "192.0.2.20"
    assert d.os_type == "linux"
    assert d.role is None
    assert d.vendor is None


def test_device_without_primary_ip():
    raw = load("device_physical.json")
    raw["primary_ip4"] = None
    raw["primary_ip"] = None
    raw["oob_ip"] = None
    d = Device.from_netbox(raw)
    assert d.main_ip is None
    assert d.oob_ip is None


def test_device_resolve_placeholders():
    d = Device.from_netbox(load("device_physical.json"))
    assert d.resolve("{name}", target_ip="192.0.2.1") == "device-01"
    assert d.resolve("{target_ip}", target_ip="192.0.2.1") == "192.0.2.1"
    assert d.resolve("{vendor}-{model}") == "acme-tower-100"
    assert d.resolve("{criticality}", target_ip="") == "3"


def test_device_resolve_for_virtual_uses_device_label_virtual():
    d = Device.from_netbox(load("device_virtual.json"))
    assert d.resolve("{device_label}") == "virtual"


# ---------------------------------------------------------------------------
# Service / _extract_service_parent_name
# ---------------------------------------------------------------------------

def test_service_42_with_virtual_machine_field():
    s = Service.from_netbox(load("service_42_vm_parent.json"))
    assert s.name == "HTTPS"
    assert s.website == "https://wiki.example.net"
    assert s.device_name == "vm-app-01"
    assert s.ports == [443]
    assert s.protocol == "tcp"
    assert s.ipaddresses == []


def test_service_with_website_and_ipaddresses():
    s = Service.from_netbox(load("service_with_website_and_ips.json"))
    assert s.name == "Web service"
    assert s.website == "https://app.example.net"
    assert s.device_name is None  # no device/virtual_machine/parent in payload
    assert s.ports == [443, 8443]
    assert s.protocol == "tcp"
    assert s.ipaddresses == ["192.0.2.21"]
    assert s.hostname == "app.example.net"
    assert s.first_ip == "192.0.2.21"


def test_service_46_parent_vm_extracts_name():
    s = Service.from_netbox(load("service_46_parent_vm.json"))
    assert s.device_name == "vm-app-01"
    assert s.website == "https://wiki.example.net"


def test_service_46_parent_device_extracts_name():
    s = Service.from_netbox(load("service_46_parent_device.json"))
    assert s.device_name == "device-01"
    assert s.ports == [623]
    assert s.ipaddresses == ["192.0.2.11"]


def test_service_no_parent_returns_none_device_name():
    s = Service.from_netbox(load("service_no_parent.json"))
    assert s.device_name is None
    assert s.ports == [22]


def test_extract_service_parent_name_all_variants():
    assert _extract_service_parent_name(
        {"device": {"name": "srv"}}
    ) == "srv"
    assert _extract_service_parent_name(
        {"device": None, "virtual_machine": {"name": "vs"}}
    ) == "vs"
    assert _extract_service_parent_name(
        {
            "parent_object_type": "virtualization.virtualmachine",
            "parent": {"name": "vs-01"},
        }
    ) == "vs-01"
    assert _extract_service_parent_name(
        {
            "parent_object_type": "dcim.device",
            "parent": {"name": "srv-01"},
        }
    ) == "srv-01"
    assert _extract_service_parent_name({"parent": {}}) is None
    assert _extract_service_parent_name({}) is None


# ---------------------------------------------------------------------------
# IpAddress.from_netbox + enrich_ip_address
# ---------------------------------------------------------------------------

def test_ipaddress_dcim_interface():
    ip = IpAddress.from_netbox(load("ipaddr_dcim_interface.json"))
    assert ip.address == "192.0.2.30"
    assert ip.device_id == 1001
    assert ip.device_name == "device-01"
    assert ip.interface_name == "eth0"
    assert ip.virtual is False


def test_ipaddress_vminterface():
    ip = IpAddress.from_netbox(load("ipaddr_vminterface.json"))
    assert ip.address == "192.0.2.20"
    assert ip.dns_name == "app.example.net"
    assert ip.device_id == 2001
    assert ip.device_name == "vm-app-01"
    assert ip.virtual is True


def test_ipaddress_unassigned_returns_empty():
    raw = load("ipaddr_dcim_interface.json")
    raw["assigned_object_type"] = ""
    raw["assigned_object"] = {}
    ip = IpAddress.from_netbox(raw)
    assert ip.device_id is None
    assert ip.device_name is None


def test_enrich_ip_address_returns_clone_with_main_ip_overridden():
    # device_physical.json — id=1001, ipaddr_dcim_interface.json attached to dev 1001
    parent = Device.from_netbox(load("device_physical.json"))
    lookup = {parent.id: parent}

    tagged = IpAddress.from_netbox(load("ipaddr_dcim_interface.json"))
    enriched = enrich_ip_address(tagged, lookup)
    assert enriched is not None
    assert enriched.main_ip == "192.0.2.30"
    assert enriched.id == parent.id
    assert enriched.name == parent.name


def test_enrich_ip_address_returns_none_when_parent_missing():
    tagged = IpAddress.from_netbox(load("ipaddr_dcim_interface.json"))
    assert enrich_ip_address(tagged, {}) is None


# ---------------------------------------------------------------------------
# Регрессионный тест на баг NetBox 4.6: поля device/virtual_machine исчезли,
# появилось parent. Гарантирует, что Service.from_netbox извлекает device_name
# в обеих версиях одинаково.
# ---------------------------------------------------------------------------

def test_regression_46_service_parent_vm_yields_same_device_name_as_42():
    s42 = Service.from_netbox(load("service_42_vm_parent.json"))
    s46 = Service.from_netbox(load("service_46_parent_vm.json"))
    assert s42.device_name == s46.device_name == "vm-app-01"
    assert s42.website == s46.website
