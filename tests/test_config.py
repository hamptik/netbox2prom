"""Tests for configuration loading and env-var handling (config.py)."""

from __future__ import annotations

import pytest
import yaml

from netbox2prom.config import Config, load_config


def _base_data() -> dict:
    return {
        "netbox": {
            "url": "https://netbox.example.com",
            "tag": "monitoring",
            "page_size": 500,
            "timeout": 15,
        },
        "prometheus": {"scrape_dir": "/tmp/prom"},
        "probe_icmp": {"targets_file": "/tmp/icmp.json"},
        "probe_http": {"targets_file": "/tmp/http.json"},
        "syslog": {"config_file": "/tmp/syslog.conf"},
    }


class TestNetboxProperties:
    def test_netbox_url(self, clean_env: None) -> None:
        cfg = Config(_base_data())
        assert cfg.netbox_url == "https://netbox.example.com"

    def test_netbox_url_default(self, clean_env: None) -> None:
        cfg = Config({})
        assert cfg.netbox_url == ""

    def test_netbox_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_TOKEN", "secret123")
        cfg = Config(_base_data())
        assert cfg.netbox_token == "secret123"

    def test_netbox_token_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETBOX_TOKEN", raising=False)
        cfg = Config(_base_data())
        with pytest.raises(ValueError, match="NETBOX_TOKEN"):
            _ = cfg.netbox_token

    def test_netbox_tag_default(self, clean_env: None) -> None:
        cfg = Config({"netbox": {}})
        assert cfg.netbox_tag == "monitoring"

    def test_netbox_tag_custom(self, clean_env: None) -> None:
        cfg = Config({"netbox": {"tag": "custom-tag"}})
        assert cfg.netbox_tag == "custom-tag"

    def test_netbox_timeout_default(self, clean_env: None) -> None:
        cfg = Config({})
        assert cfg.netbox_timeout == 30

    def test_netbox_timeout_custom(self, clean_env: None) -> None:
        cfg = Config({"netbox": {"timeout": 60}})
        assert cfg.netbox_timeout == 60


class TestNetboxPageSize:
    def test_yaml_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETBOX_PAGE_SIZE", raising=False)
        cfg = Config({"netbox": {"page_size": 250}})
        assert cfg.netbox_page_size == 250

    def test_env_overrides_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_PAGE_SIZE", "750")
        cfg = Config({"netbox": {"page_size": 250}})
        assert cfg.netbox_page_size == 750

    def test_yaml_fallback_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NETBOX_PAGE_SIZE", raising=False)
        cfg = Config({})
        assert cfg.netbox_page_size == 1000

    def test_clamped_to_minimum_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_PAGE_SIZE", "0")
        cfg = Config({})
        assert cfg.netbox_page_size == 1

    def test_negative_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_PAGE_SIZE", "-5")
        cfg = Config({})
        assert cfg.netbox_page_size == 1

    def test_invalid_env_falls_back_to_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_PAGE_SIZE", "not-a-number")
        cfg = Config({"netbox": {"page_size": 300}})
        assert cfg.netbox_page_size == 300


class TestNetboxEndpoints:
    def test_defaults(self, clean_env: None) -> None:
        cfg = Config({})
        ep = cfg.netbox_endpoints
        assert ep["devices"] == "/api/dcim/devices/"
        assert ep["virtual_machines"] == "/api/virtualization/virtual-machines/"
        assert ep["services"] == "/api/ipam/services/"

    def test_custom_merges_with_defaults(self, clean_env: None) -> None:
        cfg = Config(
            {
                "netbox": {"endpoints": {"devices": "/api/custom/devices/"}},
            }
        )
        ep = cfg.netbox_endpoints
        assert ep["devices"] == "/api/custom/devices/"
        assert ep["services"] == "/api/ipam/services/"


class TestGeneratorSections:
    def test_prometheus(self, clean_env: None) -> None:
        cfg = Config({"prometheus": {"scrape_dir": "/data"}})
        assert cfg.prometheus == {"scrape_dir": "/data"}

    def test_probe_icmp(self, clean_env: None) -> None:
        cfg = Config({"probe_icmp": {"targets_file": "/t.json"}})
        assert cfg.probe_icmp == {"targets_file": "/t.json"}

    def test_probe_icmp_falls_back_to_alloy(self, clean_env: None) -> None:
        cfg = Config({"alloy": {"targets_file": "/alloy.json"}})
        assert cfg.probe_icmp == {"targets_file": "/alloy.json"}

    def test_probe_icmp_prefers_probe_icmp_over_alloy(self, clean_env: None) -> None:
        cfg = Config(
            {
                "probe_icmp": {"targets_file": "/icmp.json"},
                "alloy": {"targets_file": "/alloy.json"},
            }
        )
        assert cfg.probe_icmp == {"targets_file": "/icmp.json"}

    def test_probe_http(self, clean_env: None) -> None:
        cfg = Config({"probe_http": {"name_field": "description"}})
        assert cfg.probe_http == {"name_field": "description"}

    def test_syslog(self, clean_env: None) -> None:
        cfg = Config({"syslog": {"block_name": "test"}})
        assert cfg.syslog == {"block_name": "test"}


class TestRuntimeEnvVars:
    def test_log_level_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        cfg = Config({})
        assert cfg.log_level == "INFO"

    def test_log_level_uppercased(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOG_LEVEL", "debug")
        cfg = Config({})
        assert cfg.log_level == "DEBUG"

    def test_poll_interval_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("POLL_INTERVAL", raising=False)
        cfg = Config({})
        assert cfg.poll_interval == 300

    def test_poll_interval_custom(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("POLL_INTERVAL", "120")
        cfg = Config({})
        assert cfg.poll_interval == 120

    def test_run_once_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RUN_ONCE", raising=False)
        cfg = Config({})
        assert cfg.run_once is False

    def test_run_once_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RUN_ONCE", "true")
        cfg = Config({})
        assert cfg.run_once is True

    def test_run_once_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RUN_ONCE", "yes")
        cfg = Config({})
        assert cfg.run_once is True

    def test_run_once_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RUN_ONCE", "1")
        cfg = Config({})
        assert cfg.run_once is True


class TestEnabledGenerators:
    def test_default_all_enabled(self, clean_env: None) -> None:
        cfg = Config({})
        assert cfg.enabled_generators == {"prometheus", "probe_icmp", "probe_http", "syslog"}

    def test_selective_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PROMETHEUS", "true")
        monkeypatch.setenv("ENABLE_SYSLOG", "false")
        cfg = Config({})
        enabled = cfg.enabled_generators
        assert "prometheus" in enabled
        assert "syslog" not in enabled
        assert "probe_icmp" not in enabled
        assert "probe_http" not in enabled

    def test_enable_alloy_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_ALLOY", "true")
        monkeypatch.setenv("ENABLE_PROMETHEUS", "false")
        monkeypatch.setenv("ENABLE_SYSLOG", "false")
        monkeypatch.setenv("ENABLE_PROBE_HTTP", "false")
        cfg = Config({})
        assert cfg.enabled_generators == {"probe_icmp"}

    def test_all_disabled_explicitly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PROMETHEUS", "false")
        monkeypatch.setenv("ENABLE_PROBE_ICMP", "false")
        monkeypatch.setenv("ENABLE_PROBE_HTTP", "false")
        monkeypatch.setenv("ENABLE_SYSLOG", "false")
        cfg = Config({})
        assert cfg.enabled_generators == set()

    def test_false_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENABLE_PROMETHEUS", "0")
        monkeypatch.setenv("ENABLE_PROBE_ICMP", "no")
        cfg = Config({})
        enabled = cfg.enabled_generators
        assert "prometheus" not in enabled
        assert "probe_icmp" not in enabled


class TestLoadConfig:
    def test_loads_valid_yaml(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            yaml.dump(
                {
                    "netbox": {"url": "https://nb.test", "tag": "test"},
                }
            )
        )
        monkeypatch.setenv("NETBOX2PROM_CONFIG", str(config_file))
        monkeypatch.setenv("NETBOX_TOKEN", "tok")

        cfg = load_config()
        assert cfg.netbox_url == "https://nb.test"
        assert cfg.netbox_tag == "test"

    def test_invalid_yaml_raises(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_file = tmp_path / "config.yml"
        config_file.write_text("just a string")
        monkeypatch.setenv("NETBOX2PROM_CONFIG", str(config_file))

        with pytest.raises(ValueError, match="Invalid configuration"):
            load_config()

    def test_missing_file_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX2PROM_CONFIG", "/nonexistent/path/config.yml")
        with pytest.raises(FileNotFoundError):
            load_config()
