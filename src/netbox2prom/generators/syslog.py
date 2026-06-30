from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile

import requests

from ..conditions import match_conditions
from ..models import Device

logger = logging.getLogger(__name__)

_PLACEHOLDERS = (
    "name",
    "ip",
    "target_ip",
    "device_label",
    "criticality",
    "os_type",
    "os",
    "main_ip",
    "oob_ip",
    "vendor",
    "model",
    "role",
    "snmp_ver",
)


def generate_syslog_config(devices: list[Device], syslog_config: dict) -> None:
    config_file = syslog_config.get("config_file")
    if not config_file:
        logger.error("Syslog config_file not configured")
        return

    block_name = syslog_config.get("block_name", "fix_hostnames")
    groups = syslog_config.get("groups", {})
    epilogue_template = syslog_config.get("epilogue_template", "")

    rules = _build_rules(devices, groups)
    content = _assemble_block(block_name, rules, epilogue_template)

    ok, msg = _validate_config(content, block_name)
    if not ok:
        logger.error("Syslog config validation failed: %s", msg)
        logger.debug("Generated content:\n%s", content)
        return

    _atomic_write(config_file, content)
    logger.info("Written %d rule(s) to %s", len(rules), config_file)


def reload_syslog(syslog_config: dict) -> None:
    reload_cfg = syslog_config.get("reload", {})
    method = reload_cfg.get("method", "none")

    if not method or method == "none":
        logger.info("Syslog reload skipped (method=none)")
        return

    if method == "http":
        _reload_http(reload_cfg)
    elif method == "signal":
        _reload_signal(reload_cfg)
    elif method == "command":
        _reload_command(reload_cfg)
    else:
        logger.warning("Unknown syslog reload method: %s", method)


def _build_rules(devices: list[Device], groups: dict) -> list[str]:
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
            rule = _substitute(template, dev, ip)
            rules.append(rule)
            logger.info("Syslog [%s]: Added rule for %s", group_name, dev.name)
    return rules


def _assemble_block(block_name: str, rules: list[str], epilogue: str) -> str:
    lines: list[str] = [f"rewrite {block_name} {{"]

    if rules:
        lines.append("\n".join(rules))

    if epilogue:
        lines.append(epilogue)

    if not rules and not epilogue:
        lines.append("    # No devices matched at this time")

    lines.append("};")
    return "\n".join(lines) + "\n"


def _substitute(template: str, dev: Device, ip: str) -> str:
    if not template:
        return ""
    name_clean = (dev.name or "").strip().replace('"', '\\"')
    values = {
        "name": name_clean,
        "ip": ip,
        "target_ip": ip,
        "device_label": "virtual" if dev.virtual else "device",
        "criticality": str(dev.criticality) if dev.criticality is not None else "",
        "os_type": dev.os_type or "",
        "os": dev.os_type or "",
        "main_ip": dev.main_ip or "",
        "oob_ip": dev.oob_ip or "",
        "vendor": dev.vendor or "",
        "model": dev.model or "",
        "role": dev.role or "",
        "snmp_ver": str(dev.snmp_ver),
    }
    result = template
    for key in _PLACEHOLDERS:
        result = result.replace("{" + key + "}", values[key])
    return result


def _validate_config(text: str, block_name: str) -> tuple[bool, str]:
    brace_ok, brace_msg = _check_braces(text)
    if not brace_ok:
        return False, f"Brace mismatch: {brace_msg}"

    marker = f"rewrite {block_name} {{"
    if marker not in text:
        return False, f"Missing '{marker}' in generated config"

    if not text.rstrip().endswith("};"):
        return False, "Generated config does not end with '};'"

    return True, ""


def _check_braces(text: str) -> tuple[bool, str]:
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, f"unexpected '}}' at position {i}"

    if in_string:
        return False, "unclosed string literal"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"

    return True, ""


def _atomic_write(path: str, content: str) -> None:
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".netbox2prom_", suffix=".conf")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _reload_http(reload_cfg: dict) -> None:
    address = reload_cfg.get("address", "")
    if not address:
        logger.warning("Syslog reload: address not configured for http method")
        return
    try:
        r = requests.post(address, timeout=10)
        if r.status_code < 400:
            logger.info("Syslog reloaded via HTTP (%d)", r.status_code)
        else:
            logger.warning("Syslog HTTP reload failed (HTTP %d)", r.status_code)
    except Exception as e:
        logger.error("Syslog HTTP reload error: %s", e)


def _reload_signal(reload_cfg: dict) -> None:
    pid_file = reload_cfg.get("pid_file", "/var/run/syslog-ng.pid")
    try:
        with open(pid_file, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except FileNotFoundError:
        logger.error("Syslog PID file not found: %s", pid_file)
        return
    except ValueError:
        logger.error("Invalid PID in %s", pid_file)
        return

    try:
        os.kill(pid, signal.SIGHUP)
        logger.info("Syslog reloaded via SIGHUP to PID %d", pid)
    except ProcessLookupError:
        logger.error("Syslog process (PID %d) not found", pid)
    except Exception as e:
        logger.error("Syslog signal reload error: %s", e)


def _reload_command(reload_cfg: dict) -> None:
    command = reload_cfg.get("command", "")
    if not command:
        logger.warning("Syslog reload: command not configured")
        return
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            logger.info("Syslog reloaded via command: %s", command)
        else:
            logger.warning(
                "Syslog reload command failed (exit %d): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except Exception as e:
        logger.error("Syslog reload command error: %s", e)
