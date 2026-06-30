from __future__ import annotations

import logging

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)


def generate_syslog_config(devices: list[Device], syslog_config: dict) -> None:
    config_file = syslog_config.get("config_file")
    block_name = syslog_config.get("block_name", "fix_hostnames")
    groups = syslog_config.get("groups", {})
    epilogue_template = syslog_config.get("epilogue_template", "")

    rules: list[str] = []
    for group_name, gcfg in groups.items():
        conditions = gcfg.get("conditions", {})
        host_field = gcfg.get("host_field", "main_ip")
        template = gcfg.get("template", "")

        for dev in devices:
            if not match_conditions(dev, conditions):
                continue
            ip = getattr(dev, host_field, None)
            if not ip or not dev.name:
                continue
            name_clean = dev.name.strip().replace('"', '\\"')
            rules.append(template.format(name=name_clean, ip=ip))
            logger.debug("Syslog [%s]: Added rule for %s", group_name, dev.name)

    if not rules:
        logger.info("No devices matched syslog rules")
        return

    new_block = f"rewrite {block_name} {{\n" + "\n".join(rules)
    if epilogue_template:
        new_block += "\n" + epilogue_template.format()
    new_block += "\n};\n\n"

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        logger.error("Syslog config file %s not found", config_file)
        return

    marker = f"rewrite {block_name} {{"
    if marker in content:
        start = content.find(marker)
        brace_count = 0
        end = start
        for i in range(start, len(content)):
            if content[i] == "{":
                brace_count += 1
            elif content[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        updated = content[:start] + new_block + content[end:]
        logger.info("Replaced '%s' block with %d rule(s) in %s", block_name, len(rules), config_file)
    elif "log {" in content:
        updated = content.replace("log {", new_block + "log {", 1)
        logger.info("Added %d rule(s) to %s", len(rules), config_file)
    else:
        updated = content.rstrip("\n") + "\n\n" + new_block
        logger.info("Appended %d rule(s) to %s", len(rules), config_file)

    with open(config_file, "w", encoding="utf-8") as f:
        f.write(updated)
