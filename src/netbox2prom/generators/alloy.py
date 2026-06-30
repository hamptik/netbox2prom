from __future__ import annotations

import json
import logging
import os

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)


def generate_alloy_targets(devices: list[Device], alloy_config: dict) -> None:
    groups = alloy_config.get("groups", {})
    default_labels = alloy_config.get("default_labels", {})
    output_file = alloy_config.get("targets_file", "/etc/alloy/blackbox_targets.json")

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
            logger.debug("Alloy [%s]: Added %s with IP %s", group_name, effective_name, target_ip)

            if gcfg.get("exclusive", False):
                skip_remaining = True

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(blocks, f, indent=4)
    logger.info("Written %d target(s) to %s", len(blocks), output_file)
