from __future__ import annotations

import logging

import requests

from .generators.syslog import reload_syslog

logger = logging.getLogger(__name__)


def reload_http(address: str, label: str) -> None:
    """Send HTTP POST /-/reload to a service (Prometheus or Alloy)."""
    try:
        r = requests.post(f"{address}/-/reload", timeout=30)
        if r.status_code == 200:
            logger.info("%s config reloaded successfully", label)
        else:
            logger.warning("Failed to reload %s (HTTP %d)", label, r.status_code)
    except Exception as e:
        logger.error("Could not reload %s: %s", label, e)


def reload_services(config, enabled: set[str], syslog_changed: bool) -> None:
    """Reload downstream services after all configs are generated.

    Each unique reload address is hit only once, so Alloy is not reloaded
    twice when both probe_icmp and probe_http are enabled.
    """
    targets: dict[str, list[str]] = {}

    if "prometheus" in enabled:
        addr = config.prometheus.get("reload_address", "")
        if addr:
            targets.setdefault(addr, []).append("prometheus")

    if "probe_icmp" in enabled:
        addr = config.probe_icmp.get("reload_address", "")
        if addr:
            targets.setdefault(addr, []).append("probe_icmp")

    if "probe_http" in enabled:
        addr = config.probe_http.get("reload_address", "")
        if addr:
            targets.setdefault(addr, []).append("probe_http")

    if "probe_tcp" in enabled:
        addr = config.probe_tcp.get("reload_address", "")
        if addr:
            targets.setdefault(addr, []).append("probe_tcp")

    for addr, generators in targets.items():
        label = " + ".join(generators) if len(generators) > 1 else generators[0]
        reload_http(addr, label)

    if "syslog" in enabled and syslog_changed:
        reload_syslog(config.syslog)
