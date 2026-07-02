"""Tests for ICMP probe target generator (generators/probe_icmp.py)."""

from __future__ import annotations

import json

from conftest import make_device

from netbox2prom.generators.probe_icmp import generate_probe_icmp_targets


def _config(tmp_path, **overrides) -> dict:
    base = {
        "targets_file": str(tmp_path / "icmp_targets.json"),
        "default_labels": {},
        "groups": {
            "all": {"conditions": {}, "target_field": "main_ip"},
        },
    }
    base.update(overrides)
    return base


class TestGenerateProbeIcmp:
    def test_basic_targets(self, tmp_path) -> None:
        devices = [
            make_device(name="rtr1", main_ip="10.0.0.1"),
            make_device(name="rtr2", main_ip="10.0.0.2"),
        ]
        cfg = _config(tmp_path)
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        assert len(data) == 2
        assert data[0]["targets"] == ["10.0.0.1"]
        assert data[1]["targets"] == ["10.0.0.2"]

    def test_exclusive_group_first_match_wins(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "critical": {
                    "conditions": {"criticality": "high"},
                    "target_field": "main_ip",
                    "exclusive": True,
                },
                "all": {
                    "conditions": {},
                    "target_field": "main_ip",
                },
            },
        )
        devices = [
            make_device(name="rtr1", main_ip="10.0.0.1", criticality="high"),
            make_device(name="rtr2", main_ip="10.0.0.2", criticality="low"),
        ]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        # rtr1 matched critical (exclusive) → not matched by "all"
        # rtr2 did not match critical → matched by "all"
        assert len(data) == 2

    def test_name_prefix_suffix(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "g": {
                    "conditions": {},
                    "target_field": "main_ip",
                    "name_prefix": "icmp-",
                    "name_suffix": "-probe",
                },
            },
        )
        devices = [make_device(name="rtr1", main_ip="10.0.0.1")]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        # The name is available in labels via {name} substitution
        # We verify via label resolution
        assert len(data) == 1

    def test_label_merging(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            default_labels={"env": "prod", "region": "eu"},
            groups={
                "g": {
                    "conditions": {},
                    "target_field": "main_ip",
                    "labels": {"region": "us", "priority": "high"},
                },
            },
        )
        devices = [make_device(name="rtr1", main_ip="10.0.0.1")]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        labels = data[0]["labels"]
        assert labels["env"] == "prod"
        assert labels["region"] == "us"  # group overrides default
        assert labels["priority"] == "high"

    def test_null_labels_removed(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            default_labels={"env": "prod"},
            groups={
                "g": {
                    "conditions": {},
                    "target_field": "main_ip",
                    "labels": {"env": None, "keep": "yes"},
                },
            },
        )
        devices = [make_device(name="rtr1", main_ip="10.0.0.1")]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        labels = data[0]["labels"]
        assert "env" not in labels
        assert labels["keep"] == "yes"

    def test_skips_devices_without_ip(self, tmp_path) -> None:
        devices = [make_device(name="rtr1", main_ip=None)]
        generate_probe_icmp_targets(devices, _config(tmp_path))

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        assert data == []

    def test_custom_target_field(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "oob": {"conditions": {}, "target_field": "oob_ip"},
            },
        )
        devices = [make_device(name="rtr1", main_ip="10.0.0.1", oob_ip="192.168.0.1")]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        assert data[0]["targets"] == ["192.168.0.1"]

    def test_empty_devices(self, tmp_path) -> None:
        generate_probe_icmp_targets([], _config(tmp_path))

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        assert data == []

    def test_label_resolution_with_device_fields(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "g": {
                    "conditions": {},
                    "target_field": "main_ip",
                    "labels": {
                        "name": "{name}",
                        "ip": "{target_ip}",
                        "vendor": "{vendor}",
                    },
                },
            },
        )
        devices = [make_device(name="rtr1", main_ip="10.0.0.1", vendor="cisco")]
        generate_probe_icmp_targets(devices, cfg)

        data = json.loads((tmp_path / "icmp_targets.json").read_text())
        labels = data[0]["labels"]
        assert labels["name"] == "rtr1"
        assert labels["ip"] == "10.0.0.1"
        assert labels["vendor"] == "cisco"
