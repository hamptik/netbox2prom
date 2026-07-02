from __future__ import annotations

import json
import logging
import os
from typing import Any

from ..conditions import match_conditions
from ..models import Service

logger = logging.getLogger(__name__)

_NAME_FIELDS = {"hostname", "description", "name", "device_name"}


def _resolve_service_name(svc: Service, name_field: str) -> str:
    if name_field == "description":
        return svc.description or svc.hostname
    if name_field == "name":
        return svc.name or svc.hostname
    if name_field == "device_name":
        return svc.device_name or svc.hostname
    return svc.hostname


def generate_probe_http_targets(services: list[Service], config: dict[str, Any]) -> None:
    groups = config.get("groups", {})
    default_labels = config.get("default_labels", {})
    output_file = config.get("targets_file", "/etc/alloy/probe_http_targets.json")
    name_field = config.get("name_field", "hostname")
    if name_field not in _NAME_FIELDS:
        logger.warning("probe_http: unknown name_field '%s', using 'hostname'", name_field)
        name_field = "hostname"

    blocks: list[dict[str, Any]] = []

    if not groups:
        groups = {"default": {}}

    for svc in services:
        skip_remaining = False
        for group_name, gcfg in groups.items():
            if skip_remaining:
                break

            conditions = gcfg.get("conditions", {})
            if conditions and not match_conditions(svc, conditions):
                continue

            if not svc.website:
                continue

            effective_name = _resolve_service_name(svc, name_field)

            labels = dict(default_labels)
            group_labels = gcfg.get("labels", {})
            labels.update(group_labels)
            labels = {k: v for k, v in labels.items() if v is not None}

            resolved_labels = {k: svc.resolve(v, name=effective_name) for k, v in labels.items()}

            blocks.append(
                {
                    "targets": [svc.website],
                    "labels": resolved_labels,
                }
            )
            logger.debug("probe_http [%s]: Added %s -> %s", group_name, effective_name, svc.website)

            if gcfg.get("exclusive", False):
                skip_remaining = True

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(blocks, f, indent=4)
    logger.info("Written %d target(s) to %s", len(blocks), output_file)
