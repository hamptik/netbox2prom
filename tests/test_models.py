"""Tests for Device and Service dataclasses (models.py)."""

from __future__ import annotations

from conftest import make_device, make_service, nb_device, nb_service

from netbox2prom.models import Device, Service, _hostname_from_url

# ---------------------------------------------------------------------------
# Device.from_netbox
# ---------------------------------------------------------------------------


class TestDeviceFromNetbox:
    def test_full_device(self) -> None:
        data = nb_device(
            name="core-sw1",
            manufacturer_slug="arista",
            type_slug="7050x3",
            role_slug="switch",
            primary_ip="10.0.0.5/24",
            oob_ip="192.168.1.5/24",
            os="eos",
            custom_fields={"snmp_ver": 3, "snmp_cipher": "aes", "criticality": "high"},
            tags=["monitoring", "core"],
        )
        dev = Device.from_netbox(data)

        assert dev.name == "core-sw1"
        assert dev.main_ip == "10.0.0.5"
        assert dev.oob_ip == "192.168.1.5"
        assert dev.os_type == "eos"
        assert dev.vendor == "arista"
        assert dev.model == "7050x3"
        assert dev.role == "switch"
        assert dev.snmp_ver == 3
        assert dev.snmp_cipher == "aes"
        assert dev.criticality == "high"
        assert dev.virtual is False
        assert dev.tags == ["monitoring", "core"]

    def test_strips_prefix_from_ips(self) -> None:
        data = nb_device(primary_ip="10.0.0.1/32", oob_ip="192.168.0.1/24")
        dev = Device.from_netbox(data)
        assert dev.main_ip == "10.0.0.1"
        assert dev.oob_ip == "192.168.0.1"

    def test_primary_ip4_takes_precedence(self) -> None:
        data = nb_device(primary_ip="10.0.0.1/24", primary_ip4="10.0.0.2/24")
        dev = Device.from_netbox(data)
        assert dev.main_ip == "10.0.0.2"

    def test_missing_ips_yield_none(self) -> None:
        data = nb_device(primary_ip=None, oob_ip=None)
        dev = Device.from_netbox(data)
        assert dev.main_ip is None
        assert dev.oob_ip is None

    def test_virtual_detection_via_vcpus(self) -> None:
        data = nb_device(vcpus=4)
        dev = Device.from_netbox(data)
        assert dev.virtual is True

    def test_physical_when_no_vcpus(self) -> None:
        data = nb_device()
        dev = Device.from_netbox(data)
        assert dev.virtual is False

    def test_missing_config_context(self) -> None:
        data = nb_device()
        data.pop("config_context")
        data["config_context"] = None
        dev = Device.from_netbox(data)
        assert dev.os_type is None

    def test_missing_device_type(self) -> None:
        data = nb_device()
        data["device_type"] = None
        dev = Device.from_netbox(data)
        assert dev.vendor is None
        assert dev.model is None

    def test_missing_role(self) -> None:
        data = nb_device()
        data["role"] = None
        dev = Device.from_netbox(data)
        assert dev.role is None

    def test_empty_tags(self) -> None:
        data = nb_device(tags=[])
        dev = Device.from_netbox(data)
        assert dev.tags == []

    def test_tags_filter_none_slugs(self) -> None:
        data = nb_device()
        data["tags"] = [{"slug": "ok"}, {"name": "no-slug"}, {"slug": "good"}]
        dev = Device.from_netbox(data)
        assert dev.tags == ["ok", "good"]

    def test_snmp_defaults_to_zero(self) -> None:
        data = nb_device()
        dev = Device.from_netbox(data)
        assert dev.snmp_ver == 0
        assert dev.snmp_cipher is None
        assert dev.criticality is None

    def test_type_slug_lowercased(self) -> None:
        data = nb_device(type_slug="Catalyst-9300")
        dev = Device.from_netbox(data)
        assert dev.model == "catalyst-9300"

    def test_empty_type_slug(self) -> None:
        data = nb_device(type_slug="")
        dev = Device.from_netbox(data)
        assert dev.model is None


# ---------------------------------------------------------------------------
# Service.from_netbox
# ---------------------------------------------------------------------------


class TestServiceFromNetbox:
    def test_full_service(self) -> None:
        data = nb_service(
            name="nginx",
            protocol={"label": "TCP", "value": "tcp"},
            description="Load balancer",
            website="https://app.example.com",
            device_name="web-01",
            tags=["prod"],
        )
        svc = Service.from_netbox(data)
        assert svc.name == "nginx"
        assert svc.protocol == "tcp"
        assert svc.description == "Load balancer"
        assert svc.website == "https://app.example.com"
        assert svc.device_name == "web-01"
        assert svc.tags == ["prod"]

    def test_protocol_as_scalar(self) -> None:
        data = nb_service(protocol="udp")
        svc = Service.from_netbox(data)
        assert svc.protocol == "udp"

    def test_protocol_none(self) -> None:
        data = nb_service(protocol_missing=True)
        svc = Service.from_netbox(data)
        assert svc.protocol is None

    def test_vm_name_extraction(self) -> None:
        data = nb_service(device_name=None, vm_name="vm-web01")
        svc = Service.from_netbox(data)
        assert svc.device_name == "vm-web01"

    def test_device_takes_precedence_over_vm(self) -> None:
        data = nb_service(device_name="phys-01", vm_name="vm-web01")
        svc = Service.from_netbox(data)
        assert svc.device_name == "phys-01"

    def test_no_device_or_vm(self) -> None:
        data = nb_service(device_name=None, vm_name=None)
        svc = Service.from_netbox(data)
        assert svc.device_name is None

    def test_custom_website_field(self) -> None:
        data = nb_service(website="https://custom.example.com", website_field="url")
        svc = Service.from_netbox(data, website_field="url")
        assert svc.website == "https://custom.example.com"

    def test_description_none_when_empty(self) -> None:
        data = nb_service(description="")
        svc = Service.from_netbox(data)
        assert svc.description is None

    def test_empty_tags(self) -> None:
        data = nb_service(tags=[])
        svc = Service.from_netbox(data)
        assert svc.tags == []


# ---------------------------------------------------------------------------
# _hostname_from_url
# ---------------------------------------------------------------------------


class TestHostnameFromUrl:
    def test_https_url(self) -> None:
        assert _hostname_from_url("https://example.com/path") == "example.com"

    def test_http_url(self) -> None:
        assert _hostname_from_url("http://example.com") == "example.com"

    def test_url_with_port(self) -> None:
        assert _hostname_from_url("https://example.com:8443/path") == "example.com"

    def test_no_scheme_returns_original(self) -> None:
        assert _hostname_from_url("example.com") == "example.com"

    def test_ip_address(self) -> None:
        assert _hostname_from_url("https://10.0.0.1/path") == "10.0.0.1"


# ---------------------------------------------------------------------------
# Service.hostname property
# ---------------------------------------------------------------------------


class TestServiceHostname:
    def test_hostname_from_website(self) -> None:
        svc = make_service(website="https://app.example.com/path")
        assert svc.hostname == "app.example.com"

    def test_empty_website(self) -> None:
        svc = make_service(website=None)
        assert svc.hostname == ""


# ---------------------------------------------------------------------------
# Device.resolve
# ---------------------------------------------------------------------------


class TestDeviceResolve:
    def test_no_placeholders(self) -> None:
        dev = make_device(name="rtr1")
        assert dev.resolve("static-template") == "static-template"

    def test_name_placeholder(self) -> None:
        dev = make_device(name="rtr1")
        assert dev.resolve("{name}") == "rtr1"

    def test_target_ip_placeholder(self) -> None:
        dev = make_device()
        assert dev.resolve("{target_ip}", target_ip="10.0.0.1") == "10.0.0.1"

    def test_name_override(self) -> None:
        dev = make_device(name="rtr1")
        assert dev.resolve("{name}", name="override") == "override"

    def test_virtual_device_label(self) -> None:
        dev = make_device(virtual=True)
        assert dev.resolve("{device_label}") == "virtual"

    def test_physical_device_label(self) -> None:
        dev = make_device(virtual=False)
        assert dev.resolve("{device_label}") == "device"

    def test_missing_field_yields_empty(self) -> None:
        dev = make_device(name=None, main_ip=None)
        assert dev.resolve("{name}-{main_ip}") == "-"

    def test_criticality_none_yields_empty(self) -> None:
        dev = make_device(criticality=None)
        assert dev.resolve("{criticality}") == ""

    def test_criticality_value(self) -> None:
        dev = make_device(criticality="high")
        assert dev.resolve("{criticality}") == "high"

    def test_os_type_and_os_alias(self) -> None:
        dev = make_device(os_type="linux")
        assert dev.resolve("{os_type}") == "linux"
        assert dev.resolve("{os}") == "linux"

    def test_snmp_ver(self) -> None:
        dev = make_device(snmp_ver=3)
        assert dev.resolve("{snmp_ver}") == "3"

    def test_all_fields(self) -> None:
        dev = make_device(
            name="sw1",
            main_ip="10.0.0.1",
            oob_ip="192.168.0.1",
            vendor="cisco",
            model="cat9300",
            role="switch",
            os_type="iosxe",
            snmp_ver=2,
            criticality="high",
        )
        result = dev.resolve(
            "{name}|{main_ip}|{oob_ip}|{vendor}|{model}|{role}|{os}|{snmp_ver}|{criticality}"
        )
        assert result == "sw1|10.0.0.1|192.168.0.1|cisco|cat9300|switch|iosxe|2|high"


# ---------------------------------------------------------------------------
# Service.resolve
# ---------------------------------------------------------------------------


class TestServiceResolve:
    def test_no_placeholders(self) -> None:
        svc = make_service()
        assert svc.resolve("static") == "static"

    def test_website_placeholder(self) -> None:
        svc = make_service(website="https://app.example.com")
        assert svc.resolve("{website}") == "https://app.example.com"

    def test_name_falls_back_to_hostname(self) -> None:
        svc = make_service(website="https://app.example.com", name=None, description=None)
        assert svc.resolve("{name}") == "app.example.com"

    def test_name_falls_back_to_description(self) -> None:
        svc = make_service(website=None, description="My Service", name=None)
        assert svc.resolve("{name}") == "My Service"

    def test_name_override(self) -> None:
        svc = make_service()
        assert svc.resolve("{name}", name="custom-name") == "custom-name"

    def test_description_placeholder(self) -> None:
        svc = make_service(description="Web Server")
        assert svc.resolve("{description}") == "Web Server"

    def test_device_name_placeholder(self) -> None:
        svc = make_service(device_name="host1")
        assert svc.resolve("{device_name}") == "host1"

    def test_protocol_placeholder(self) -> None:
        svc = make_service(protocol="tcp")
        assert svc.resolve("{protocol}") == "tcp"

    def test_service_name_placeholder(self) -> None:
        svc = make_service(name="nginx")
        assert svc.resolve("{service_name}") == "nginx"
