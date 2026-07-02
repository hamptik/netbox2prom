from __future__ import annotations

import logging
import os
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_ENDPOINTS = {
    "devices": "/api/dcim/devices/",
    "virtual_machines": "/api/virtualization/virtual-machines/",
    "services": "/api/ipam/services/",
}

_TRUE_VALUES = {"true", "1", "yes"}
_FALSE_VALUES = {"false", "0", "no"}


class Config:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    @property
    def netbox(self) -> dict[str, Any]:
        return self._data.get("netbox", {})

    @property
    def netbox_url(self) -> str:
        return self.netbox.get("url", "")

    @property
    def netbox_token(self) -> str:
        token = os.getenv("NETBOX_TOKEN", "")
        if not token:
            raise ValueError("NETBOX_TOKEN environment variable is required")
        return token

    @property
    def netbox_tag(self) -> str:
        return self.netbox.get("tag", "monitoring")

    @property
    def netbox_endpoints(self) -> dict[str, str]:
        endpoints = self.netbox.get("endpoints", {})
        return {**_DEFAULT_ENDPOINTS, **endpoints}

    @property
    def netbox_timeout(self) -> int:
        return int(self.netbox.get("timeout", 30))

    @property
    def netbox_page_size(self) -> int:
        raw = os.getenv("NETBOX_PAGE_SIZE")
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                logger.warning("Invalid NETBOX_PAGE_SIZE=%r, ignoring", raw)
        return max(1, int(self.netbox.get("page_size", 1000)))

    @property
    def prometheus(self) -> dict[str, Any]:
        return self._data.get("prometheus", {})

    @property
    def probe_icmp(self) -> dict[str, Any]:
        return self._data.get("probe_icmp") or self._data.get("alloy", {})

    @property
    def probe_http(self) -> dict[str, Any]:
        return self._data.get("probe_http", {})

    @property
    def syslog(self) -> dict[str, Any]:
        return self._data.get("syslog", {})

    @property
    def log_level(self) -> str:
        return os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def poll_interval(self) -> int:
        return int(os.getenv("POLL_INTERVAL", "300"))

    @property
    def run_once(self) -> bool:
        return os.getenv("RUN_ONCE", "false").lower() in _TRUE_VALUES

    @property
    def enabled_generators(self) -> set[str]:
        env_map = {
            "ENABLE_PROMETHEUS": "prometheus",
            "ENABLE_PROBE_ICMP": "probe_icmp",
            "ENABLE_ALLOY": "probe_icmp",
            "ENABLE_PROBE_HTTP": "probe_http",
            "ENABLE_SYSLOG": "syslog",
        }
        enabled: set[str] = set()
        any_set = False
        for env_var, name in env_map.items():
            val = os.getenv(env_var, "").lower().strip()
            if val in _TRUE_VALUES:
                enabled.add(name)
                any_set = True
            elif val in _FALSE_VALUES:
                any_set = True
        if not any_set:
            enabled = {"prometheus", "probe_icmp", "probe_http", "syslog"}
        return enabled


def load_config() -> Config:
    config_path = os.getenv("NETBOX2PROM_CONFIG", "/etc/netbox2prom/config.yml")
    logger.info("Loading configuration from %s", config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid configuration file: {config_path}")
    return Config(data)
