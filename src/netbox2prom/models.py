from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Device:
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
