from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)


def _iter_device_targets(
    dev: Device,
    groups: dict,
    default_labels: dict,
    target_ip_override: str | None = None,
) -> Iterator[tuple[str, str, dict]]:
    """Yield *(group_name, target_ip, block)* for every group *dev* matches."""
    skip_remaining = False
    for group_name, gcfg in groups.items():
        if skip_remaining:
            break

        conditions = gcfg.get("conditions", {})
        if not match_conditions(dev, conditions):
            continue

        if target_ip_override is not None:
            target_ip = target_ip_override
        else:
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

        yield group_name, target_ip, {
            "targets": [target_ip],
            "labels": resolved_labels,
        }

        if gcfg.get("exclusive", False):
            skip_remaining = True


def generate_probe_icmp_targets(
    devices: list[Device],
    ip_devices: list[Device],
    config: dict,
) -> None:
    groups = config.get("groups", {})
    default_labels = config.get("default_labels", {})
    output_file = config.get("targets_file", "/etc/alloy/blackbox_targets.json")

    blocks: list[dict] = []
    seen_ips: set[str] = set()

    for dev in devices:
        for group_name, target_ip, block in _iter_device_targets(
            dev, groups, default_labels
        ):
            if target_ip in seen_ips:
                logger.debug(
                    "probe_icmp: Skipping duplicate IP %s for %s",
                    target_ip, dev.name,
                )
                continue
            blocks.append(block)
            seen_ips.add(target_ip)
            logger.debug(
                "probe_icmp [%s]: Added %s with IP %s",
                group_name, dev.name, target_ip,
            )

    for dev in ip_devices:
        if dev.main_ip in seen_ips:
            logger.debug(
                "probe_icmp: Skipping tagged IP %s for %s (already monitored)",
                dev.main_ip, dev.name,
            )
            continue
        matched = False
        for group_name, target_ip, block in _iter_device_targets(
            dev, groups, default_labels, target_ip_override=dev.main_ip
        ):
            blocks.append(block)
            seen_ips.add(target_ip)
            matched = True
            logger.debug(
                "probe_icmp [%s]: Added %s with tagged IP %s",
                group_name, dev.name, target_ip,
            )
        if not matched and dev.main_ip:
            logger.debug(
                "probe_icmp: Tagged IP %s (%s) matched no group",
                dev.main_ip, dev.name,
            )

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(blocks, f, indent=4)
    logger.info("Written %d target(s) to %s", len(blocks), output_file)
