from __future__ import annotations

import logging
import sys
import time

from .config import load_config
from .log import setup_logging
from .netbox_client import NetBoxClient
from .reload import reload_services
from .generators.probe_icmp import generate_probe_icmp_targets
from .generators.probe_http import generate_probe_http_targets
from .generators.probe_tcp import generate_probe_tcp_targets
from .generators.prometheus import generate_prometheus_configs
from .generators.syslog import generate_syslog_config

logger = logging.getLogger(__name__)


def run_once(config) -> None:
    enabled = config.enabled_generators
    client = NetBoxClient(config)

    need_devices = bool(enabled & {"prometheus", "probe_icmp", "syslog"})
    need_services = bool(enabled & {"probe_http", "probe_tcp"})

    devices = client.get_devices() if need_devices else []
    services = []
    if need_services:
        website_field = config.probe_http.get("website_field", "website")
        services = client.get_services(website_field=website_field)

    syslog_changed = False

    if "prometheus" in enabled:
        logger.info("=== Prometheus generator ===")
        generate_prometheus_configs(devices, config.prometheus)

    if "probe_icmp" in enabled:
        logger.info("=== probe_icmp generator ===")
        generate_probe_icmp_targets(devices, config.probe_icmp)

    if "probe_http" in enabled:
        logger.info("=== probe_http generator ===")
        generate_probe_http_targets(services, config.probe_http)

    if "probe_tcp" in enabled:
        logger.info("=== probe_tcp generator ===")
        generate_probe_tcp_targets(services, config.probe_tcp)

    if "syslog" in enabled:
        logger.info("=== Syslog generator ===")
        syslog_changed = generate_syslog_config(devices, config.syslog)

    logger.info("=== Reloading services ===")
    reload_services(config, enabled, syslog_changed)


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    enabled = config.enabled_generators
    if not enabled:
        logger.error(
            "No generators enabled. Set at least one of: "
            "ENABLE_PROMETHEUS=true, ENABLE_PROBE_ICMP=true, "
            "ENABLE_PROBE_HTTP=true, ENABLE_SYSLOG=true"
        )
        sys.exit(1)

    logger.info("Enabled generators: %s", ", ".join(sorted(enabled)))

    if config.run_once:
        logger.info("Running in single-run mode")
        run_once(config)
        return

    interval = config.poll_interval
    logger.info("Starting poll loop (interval=%ds)", interval)
    while True:
        try:
            run_once(config)
        except Exception:
            logger.error("Error during generation", exc_info=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
