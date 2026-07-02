"""Tests for Prometheus SNMP scrape config generator (generators/prometheus.py)."""

from __future__ import annotations

import yaml
from conftest import make_device

from netbox2prom.generators.prometheus import (
    _build_relabel_configs,
    generate_prometheus_configs,
)


def _config(tmp_path, **overrides) -> dict:
    base = {
        "scrape_dir": str(tmp_path / "prom"),
        "snmp_exporter_address": "snmp-exporter:9116",
        "metrics_path": "/snmp",
        "groups": {
            "routers": {
                "conditions": {"role": "router"},
                "ip_field": "oob_ip",
                "scrape_interval": "2m",
            },
        },
    }
    base.update(overrides)
    return base


class TestGeneratePrometheus:
    def test_writes_matching_devices(self, tmp_path) -> None:
        devices = [
            make_device(name="rtr1", role="router", oob_ip="10.0.0.1"),
            make_device(name="rtr2", role="router", oob_ip="10.0.0.2"),
            make_device(name="sw1", role="switch", oob_ip="10.0.0.3"),
        ]
        generate_prometheus_configs(devices, _config(tmp_path))

        out_file = tmp_path / "prom" / "routers.yml"
        assert out_file.exists()

        doc = yaml.safe_load(out_file.read_text())
        scrape = doc["scrape_configs"][0]
        assert scrape["job_name"] == "routers"
        assert scrape["scrape_interval"] == "2m"
        assert len(scrape["static_configs"]) == 2
        ips = [sc["targets"][0] for sc in scrape["static_configs"]]
        assert ips == ["10.0.0.1", "10.0.0.2"]

    def test_skips_devices_without_ip(self, tmp_path) -> None:
        devices = [
            make_device(name="rtr1", role="router", oob_ip=None),
        ]
        generate_prometheus_configs(devices, _config(tmp_path))

        out_file = tmp_path / "prom" / "routers.yml"
        assert not out_file.exists()

    def test_deletes_file_when_no_matches(self, tmp_path) -> None:
        scrape_dir = tmp_path / "prom"
        scrape_dir.mkdir(parents=True)
        stale_file = scrape_dir / "routers.yml"
        stale_file.write_text("old content")

        devices = [make_device(name="sw1", role="switch")]
        generate_prometheus_configs(devices, _config(tmp_path))

        assert not stale_file.exists()

    def test_creates_output_dir(self, tmp_path) -> None:
        devices = []
        cfg = _config(tmp_path)
        generate_prometheus_configs(devices, cfg)

        assert (tmp_path / "prom").is_dir()

    def test_default_labels_resolved(self, tmp_path) -> None:
        devices = [make_device(name="rtr1", role="router", oob_ip="10.0.0.1")]
        cfg = _config(tmp_path, default_labels={"job": "snmp-{name}"})
        generate_prometheus_configs(devices, cfg)

        doc = yaml.safe_load((tmp_path / "prom" / "routers.yml").read_text())
        labels = doc["scrape_configs"][0]["static_configs"][0]["labels"]
        assert labels["job"] == "snmp-rtr1"

    def test_multiple_groups(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "routers": {"conditions": {"role": "router"}},
                "switches": {"conditions": {"role": "switch"}},
            },
        )
        devices = [
            make_device(name="rtr1", role="router", oob_ip="10.0.0.1"),
            make_device(name="sw1", role="switch", oob_ip="10.0.0.2"),
        ]
        generate_prometheus_configs(devices, cfg)

        assert (tmp_path / "prom" / "routers.yml").exists()
        assert (tmp_path / "prom" / "switches.yml").exists()

    def test_ip_field_custom(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "main": {"conditions": {}, "ip_field": "main_ip"},
            },
        )
        devices = [
            make_device(name="rtr1", main_ip="172.16.0.1", oob_ip=None),
        ]
        generate_prometheus_configs(devices, cfg)

        doc = yaml.safe_load((tmp_path / "prom" / "main.yml").read_text())
        assert doc["scrape_configs"][0]["static_configs"][0]["targets"] == ["172.16.0.1"]


class TestBuildRelabelConfigs:
    def test_base_configs(self) -> None:
        relabels = _build_relabel_configs({}, "localhost:9116")
        assert len(relabels) == 3
        assert relabels[0]["source_labels"] == ["__address__"]
        assert relabels[1]["replacement"] == "localhost:9116"

    def test_device_type_added(self) -> None:
        relabels = _build_relabel_configs({"device_type": "router"}, "snmp:9116")
        dt = [r for r in relabels if r.get("target_label") == "device_type"]
        assert len(dt) == 1
        assert dt[0]["replacement"] == "router"

    def test_vendor_added(self) -> None:
        relabels = _build_relabel_configs({"vendor": "cisco"}, "snmp:9116")
        v = [r for r in relabels if r.get("target_label") == "vendor"]
        assert len(v) == 1
        assert v[0]["replacement"] == "cisco"

    def test_custom_relabel_extended(self) -> None:
        custom = [{"target_label": "env", "replacement": "prod", "action": "replace"}]
        relabels = _build_relabel_configs({"relabel_configs": custom}, "snmp:9116")
        assert relabels[-1]["target_label"] == "env"
