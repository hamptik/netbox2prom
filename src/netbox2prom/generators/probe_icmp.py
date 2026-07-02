from __future__ import annotations

import json
import logging
import os

import requests

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)


def generate_probe_icmp_targets(devices: list[Device], config: dict) -> None:
    groups = config.get("groups", {})
    default_labels = config.get("default_labels", {})
    output_file = config.get("targets_file", "/etc/alloy/blackbox_targets.json")

    blocks: list[dict] = []

    for dev in devices:
        skip_remaining = False
        for group_name, gcfg in groups.items():
            if skip_remaining:
                break

            conditions = gcfg.get("conditions", {})
            if not match_conditions(dev, conditions):
                continue

            target_field = gcfg.get("target_field", "main_ip")
            target_ip = getattr(dev, target_field, None)
            if not target_ip:
                continue

            name_prefix = gcfg.get("name_prefix", "")
            name_suffix = gcfg.get("name_suffix", "")
            effective_name = f"{name_prefix}{dev.name or ''}{name_suffix}"

            labels = dict(default_labels)
            group_labels = gcfg.get("labels", {})
            labels.update(group_labels)
            labels = {k: v for k, v in labels.items() if v is not None}

            resolved_labels = {
                k: dev.resolve(v, target_ip=target_ip, name=effective_name)
                for k, v in labels.items()
            }

            blocks.append({
                "targets": [target_ip],
                "labels": resolved_labels,
            })
            logger.debug("probe_icmp [%s]: Added %s with IP %s", group_name, effective_name, target_ip)

            if gcfg.get("exclusive", False):
                skip_remaining = True

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(blocks, f, indent=4)
    logger.info("Written %d target(s) to %s", len(blocks), output_file)


def reload_probe_icmp(config: dict) -> None:
    address = config.get("reload_address")
    if not address:
        logger.info("probe_icmp reload skipped (reload_address not configured)")
        return
    try:
        r = requests.post(f"{address}/-/reload", timeout=30)
        if r.status_code == 200:
            logger.info("probe_icmp config reloaded successfully")
        else:
            logger.warning("Failed to reload probe_icmp (HTTP %d)", r.status_code)
    except Exception as e:
        logger.error("Could not reload probe_icmp: %s", e)
