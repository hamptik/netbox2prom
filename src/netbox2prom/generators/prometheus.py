from __future__ import annotations

import logging
import os

import yaml

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)


def generate_prometheus_configs(devices: list[Device], prometheus_config: dict) -> None:
    groups = prometheus_config.get("groups", {})
    snmp_exporter_address = prometheus_config.get("snmp_exporter_address", "localhost:9116")
    metrics_path = prometheus_config.get("metrics_path", "/snmp")
    out_dir = prometheus_config.get("scrape_dir", "./prometheus_scrape")
    default_labels = prometheus_config.get("default_labels", {})

    os.makedirs(out_dir, exist_ok=True)

    for group_name, gcfg in groups.items():
        conditions = gcfg.get("conditions", {})
        ip_field = gcfg.get("ip_field", "oob_ip")

        job = {
            "job_name": group_name,
            "scrape_interval": gcfg.get("scrape_interval", "5m"),
            "scrape_timeout": gcfg.get("scrape_timeout", "4m"),
            "metrics_path": metrics_path,
            "params": gcfg.get("params", {}),
            "static_configs": [],
            "relabel_configs": _build_relabel_configs(gcfg, snmp_exporter_address),
        }

        for dev in devices:
            if not match_conditions(dev, conditions):
                continue
            target_ip = getattr(dev, ip_field, None)
            if not target_ip:
                continue

            labels = {}
            for k, v in default_labels.items():
                labels[k] = dev.resolve(v, target_ip=target_ip)

            job["static_configs"].append({
                "targets": [target_ip],
                "labels": labels,
            })
            logger.debug("Prometheus [%s]: Added %s with IP %s", group_name, dev.name, target_ip)

        filename = os.path.join(out_dir, f"{group_name}.yml")

        if not job["static_configs"]:
            if os.path.exists(filename):
                os.remove(filename)
                logger.info("Removed empty file %s", filename)
            continue

        doc = {"scrape_configs": [job]}
        with open(filename, "w", encoding="utf-8") as f:
            yaml.safe_dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        logger.info("Written %s with %d target(s)", filename, len(job["static_configs"]))


def _build_relabel_configs(gcfg: dict, snmp_exporter_address: str) -> list[dict]:
    relabel_configs = [
        {"source_labels": ["__address__"], "target_label": "__param_target", "action": "replace"},
        {"target_label": "__address__", "replacement": snmp_exporter_address, "action": "replace"},
        {"source_labels": ["__param_target"], "target_label": "node_ip", "action": "replace"},
    ]
    if "device_type" in gcfg:
        relabel_configs.append({
            "target_label": "device_type",
            "replacement": gcfg["device_type"],
            "action": "replace",
        })
    if "vendor" in gcfg:
        relabel_configs.append({
            "target_label": "vendor",
            "replacement": gcfg["vendor"],
            "action": "replace",
        })
    relabel_configs.extend(gcfg.get("relabel_configs", []))
    return relabel_configs
