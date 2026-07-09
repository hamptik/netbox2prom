from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Optional
from urllib.parse import urlparse


@dataclass
class Device:
    id: Optional[int] = None
    name: Optional[str] = None
    main_ip: Optional[str] = None
    oob_ip: Optional[str] = None
    os_type: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    role: Optional[str] = None
    snmp_ver: int = 0
    snmp_cipher: Any = None
    criticality: Any = None
    virtual: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_netbox(cls, data: dict) -> Device:
        config_context = data.get("config_context") or {}
        device_type = data.get("device_type") or {}
        manufacturer = device_type.get("manufacturer") or {}
        custom_fields = data.get("custom_fields") or {}
        role_obj = data.get("role") or {}

        oob_ip_obj = data.get("oob_ip")
        oob_ip = oob_ip_obj["address"].split("/")[0] if oob_ip_obj and oob_ip_obj.get("address") else None

        primary_ip_obj = data.get("primary_ip4") or data.get("primary_ip") or {}
        main_ip = primary_ip_obj["address"].split("/")[0] if primary_ip_obj and primary_ip_obj.get("address") else None

        type_slug = device_type.get("slug") or ""
        model = type_slug.lower() if type_slug else None

        return cls(
            id=data.get("id"),
            name=data.get("name"),
            main_ip=main_ip,
            oob_ip=oob_ip,
            os_type=config_context.get("os"),
            vendor=manufacturer.get("slug"),
            model=model,
            role=role_obj.get("slug"),
            snmp_ver=custom_fields.get("snmp_ver", 0),
            snmp_cipher=custom_fields.get("snmp_cipher"),
            criticality=custom_fields.get("criticality"),
            virtual="vcpus" in data,
            tags=[t.get("slug") for t in data.get("tags", []) if t.get("slug")],
        )

    def resolve(self, template: str, target_ip: str = "", name: str = "") -> str:
        if "{" not in template:
            return template
        return template.format(
            name=name or self.name or "",
            target_ip=target_ip,
            device_label="virtual" if self.virtual else "device",
            criticality=str(self.criticality) if self.criticality is not None else "",
            os_type=self.os_type or "",
            os=self.os_type or "",
            main_ip=self.main_ip or "",
            oob_ip=self.oob_ip or "",
            vendor=self.vendor or "",
            model=self.model or "",
            role=self.role or "",
            snmp_ver=str(self.snmp_ver),
        )


def _hostname_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or url


@dataclass
class Service:
    name: Optional[str] = None
    protocol: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    device_name: Optional[str] = None
    ports: list[int] = field(default_factory=list)
    ipaddresses: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_netbox(cls, data: dict, website_field: str = "website") -> Service:
        custom_fields = data.get("custom_fields") or {}
        website = custom_fields.get(website_field)

        protocol_obj = data.get("protocol") or {}

        device_obj = data.get("device")
        vm_obj = data.get("virtual_machine")
        device_name = None
        if device_obj and device_obj.get("name"):
            device_name = device_obj["name"]
        elif vm_obj and vm_obj.get("name"):
            device_name = vm_obj["name"]

        ports = [p for p in data.get("ports", []) if isinstance(p, int)]

        ip_list = data.get("ipaddresses") or []
        ipaddresses: list[str] = []
        for ip_obj in ip_list:
            addr = ip_obj.get("address") if isinstance(ip_obj, dict) else None
            if addr:
                ipaddresses.append(addr.split("/")[0])

        return cls(
            name=data.get("name"),
            protocol=protocol_obj.get("value") if isinstance(protocol_obj, dict) else protocol_obj,
            description=data.get("description") or None,
            website=website,
            device_name=device_name,
            ports=ports,
            ipaddresses=ipaddresses,
            tags=[t.get("slug") for t in data.get("tags", []) if t.get("slug")],
        )

    @property
    def hostname(self) -> str:
        if not self.website:
            return ""
        return _hostname_from_url(self.website)

    @property
    def first_ip(self) -> Optional[str]:
        return self.ipaddresses[0] if self.ipaddresses else None

    def resolve(self, template: str, name: str = "", port: int = 0) -> str:
        if "{" not in template:
            return template
        return template.format(
            name=name or self.hostname or self.description or "",
            website=self.website or "",
            description=self.description or "",
            device_name=self.device_name or "",
            protocol=self.protocol or "",
            port=str(port) if port else "",
            ip=self.first_ip or "",
            service_name=self.name or "",
        )


@dataclass
class IpAddress:
    """An IP address from NetBox IPAM (``/api/ipam/ip-addresses/``)."""

    address: str
    dns_name: str = ""
    device_id: Optional[int] = None
    device_name: Optional[str] = None
    interface_name: Optional[str] = None
    virtual: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_netbox(cls, data: dict) -> "IpAddress":
        raw_addr = data.get("address") or ""
        address = raw_addr.split("/")[0] if raw_addr else ""

        assigned_type = data.get("assigned_object_type") or ""
        assigned_obj = data.get("assigned_object") or {}

        device_id: Optional[int] = None
        device_name: Optional[str] = None
        interface_name = assigned_obj.get("name")
        virtual = False

        if "vminterface" in assigned_type:
            virtual = True
            vm = assigned_obj.get("virtual_machine") or {}
            device_id = vm.get("id")
            device_name = vm.get("name")
        elif assigned_obj:
            dev = assigned_obj.get("device") or {}
            device_id = dev.get("id")
            device_name = dev.get("name")

        return cls(
            address=address,
            dns_name=data.get("dns_name") or "",
            device_id=device_id,
            device_name=device_name,
            interface_name=interface_name,
            virtual=virtual,
            tags=[t.get("slug") for t in data.get("tags", []) if t.get("slug")],
        )


def enrich_ip_address(
    ip: "IpAddress", device_lookup: dict[int, Device]
) -> Optional[Device]:
    """Create a Device clone with ``main_ip`` set to the tagged IP address.

    Returns ``None`` when the parent device is not in *device_lookup* (i.e. it
    does not carry the monitoring tag and was not fetched).
    """
    parent = device_lookup.get(ip.device_id) if ip.device_id is not None else None
    if parent is None:
        return None
    return replace(parent, main_ip=ip.address)
