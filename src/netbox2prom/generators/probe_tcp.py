from __future__ import annotations

import json
import logging
import os

from ..conditions import match_conditions
from ..models import Service

logger = logging.getLogger(__name__)


def generate_probe_tcp_targets(services: list[Service], config: dict) -> None:
    groups = config.get("groups", {})
    default_labels = config.get("default_labels", {})
    output_file = config.get("targets_file", "/etc/alloy/probe_tcp_targets.json")

    if not groups:
        groups = {"default": {}}

    blocks: list[dict] = []

    for svc in services:
        if svc.website:
            continue

        if svc.protocol and svc.protocol != "tcp":
            logger.debug(
                "probe_tcp: skipping %s — protocol %s not supported",
                svc.name,
                svc.protocol,
            )
            continue

        if not svc.ipaddresses:
            logger.debug("probe_tcp: skipping %s — no ipaddresses", svc.name)
            continue

        if not svc.ports:
            logger.debug("probe_tcp: skipping %s — no ports", svc.name)
            continue

        ip = svc.first_ip

        skip_remaining = False
        for group_name, gcfg in groups.items():
            if skip_remaining:
                break

            conditions = gcfg.get("conditions", {})
            if conditions and not match_conditions(svc, conditions):
                continue

            group_labels = gcfg.get("labels", {})

            for port in svc.ports:
                target = f"{ip}:{port}"

                effective_name = f"{svc.device_name or svc.name}:{port}"

                labels = dict(default_labels)
                labels.update(group_labels)
                labels = {k: v for k, v in labels.items() if v is not None}

                resolved_labels = {
                    k: svc.resolve(v, name=effective_name, port=port)
                    for k, v in labels.items()
                }

                blocks.append(
                    {
                        "targets": [target],
                        "labels": resolved_labels,
                    }
                )
                logger.debug(
                    "probe_tcp [%s]: Added %s -> %s",
                    group_name,
                    effective_name,
                    target,
                )

            if gcfg.get("exclusive", False):
                skip_remaining = True

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(blocks, f, indent=4)
    logger.info("Written %d target(s) to %s", len(blocks), output_file)
