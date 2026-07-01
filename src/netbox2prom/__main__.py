from __future__ import annotations

import logging
import sys
import time

from .config import load_config
from .log import setup_logging
from .netbox_client import NetBoxClient
from .generators.alloy import generate_alloy_targets, reload_alloy
from .generators.prometheus import generate_prometheus_configs, reload_prometheus
from .generators.syslog import generate_syslog_config, reload_syslog

logger = logging.getLogger(__name__)


def run_once(config) -> None:
    enabled = config.enabled_generators

    client = NetBoxClient(config)
    devices = client.get_devices()

    if "prometheus" in enabled:
        logger.info("=== Prometheus generator ===")
        generate_prometheus_configs(devices, config.prometheus)
        reload_prometheus(config.prometheus)

    if "alloy" in enabled:
        logger.info("=== Alloy generator ===")
        generate_alloy_targets(devices, config.alloy)
        reload_alloy(config.alloy)

    if "syslog" in enabled:
        logger.info("=== Syslog generator ===")
        changed = generate_syslog_config(devices, config.syslog)
        if changed:
            reload_syslog(config.syslog)


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    enabled = config.enabled_generators
    if not enabled:
        logger.error(
            "No generators enabled. Set at least one of: "
            "ENABLE_PROMETHEUS=true, ENABLE_ALLOY=true, ENABLE_SYSLOG=true"
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
