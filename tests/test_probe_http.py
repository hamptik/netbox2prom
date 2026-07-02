"""Tests for HTTP probe target generator (generators/probe_http.py)."""

from __future__ import annotations

import json

from conftest import make_service

from netbox2prom.generators.probe_http import (
    _resolve_service_name,
    generate_probe_http_targets,
)


def _config(tmp_path, **overrides) -> dict:
    base = {
        "targets_file": str(tmp_path / "http_targets.json"),
        "default_labels": {},
        "name_field": "hostname",
        "groups": {},
    }
    base.update(overrides)
    return base


class TestResolveServiceName:
    def test_hostname_default(self) -> None:
        svc = make_service(website="https://app.example.com")
        assert _resolve_service_name(svc, "hostname") == "app.example.com"

    def test_description(self) -> None:
        svc = make_service(description="My App", website="https://app.example.com")
        assert _resolve_service_name(svc, "description") == "My App"

    def test_description_falls_back_to_hostname(self) -> None:
        svc = make_service(description=None, website="https://app.example.com")
        assert _resolve_service_name(svc, "description") == "app.example.com"

    def test_name(self) -> None:
        svc = make_service(name="nginx", website="https://app.example.com")
        assert _resolve_service_name(svc, "name") == "nginx"

    def test_name_falls_back_to_hostname(self) -> None:
        svc = make_service(name=None, website="https://app.example.com")
        assert _resolve_service_name(svc, "name") == "app.example.com"

    def test_device_name(self) -> None:
        svc = make_service(device_name="host1", website="https://app.example.com")
        assert _resolve_service_name(svc, "device_name") == "host1"

    def test_device_name_falls_back_to_hostname(self) -> None:
        svc = make_service(device_name=None, website="https://app.example.com")
        assert _resolve_service_name(svc, "device_name") == "app.example.com"


class TestGenerateProbeHttp:
    def test_basic_targets_no_groups(self, tmp_path) -> None:
        services = [
            make_service(website="https://app1.example.com"),
            make_service(website="https://app2.example.com"),
        ]
        generate_probe_http_targets(services, _config(tmp_path))

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert len(data) == 2
        assert data[0]["targets"] == ["https://app1.example.com"]
        assert data[1]["targets"] == ["https://app2.example.com"]

    def test_skips_services_without_website(self, tmp_path) -> None:
        services = [
            make_service(website="https://app1.example.com"),
            make_service(website=None),
        ]
        generate_probe_http_targets(services, _config(tmp_path))

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert len(data) == 1

    def test_label_merging(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            default_labels={"env": "prod"},
            groups={
                "g": {"conditions": {}, "labels": {"region": "eu"}},
            },
        )
        services = [make_service(website="https://app.example.com")]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        labels = data[0]["labels"]
        assert labels["env"] == "prod"
        assert labels["region"] == "eu"

    def test_null_labels_removed(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            default_labels={"env": "prod"},
            groups={
                "g": {"conditions": {}, "labels": {"env": None}},
            },
        )
        services = [make_service(website="https://app.example.com")]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert "env" not in data[0]["labels"]

    def test_exclusive_group(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "prod": {"conditions": {}, "exclusive": True},
                "all": {"conditions": {}},
            },
        )
        services = [make_service(website="https://app.example.com")]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert len(data) == 1  # only matched once due to exclusive

    def test_conditions_filtering(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            groups={
                "tcp": {"conditions": {"protocol": "tcp"}},
            },
        )
        services = [
            make_service(website="https://app1.example.com", protocol="tcp"),
            make_service(website="https://app2.example.com", protocol="udp"),
        ]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert len(data) == 1
        assert data[0]["targets"] == ["https://app1.example.com"]

    def test_empty_services(self, tmp_path) -> None:
        generate_probe_http_targets([], _config(tmp_path))

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert data == []

    def test_name_field_in_labels(self, tmp_path) -> None:
        cfg = _config(
            tmp_path,
            name_field="description",
            groups={"g": {"conditions": {}, "labels": {"name": "{name}"}}},
        )
        services = [
            make_service(description="My App", website="https://app.example.com"),
        ]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert data[0]["labels"]["name"] == "My App"

    def test_unknown_name_field_falls_back_to_hostname(self, tmp_path) -> None:
        cfg = _config(tmp_path, name_field="bogus")
        services = [make_service(website="https://app.example.com")]
        generate_probe_http_targets(services, cfg)

        data = json.loads((tmp_path / "http_targets.json").read_text())
        assert len(data) == 1
