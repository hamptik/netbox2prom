"""Tests for __main__.py run_once orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from netbox2prom.__main__ import run_once
from netbox2prom.config import Config


def _full_config(tmp_path) -> Config:
    return Config(
        {
            "netbox": {"url": "https://nb.test", "tag": "mon", "page_size": 50},
            "prometheus": {"scrape_dir": str(tmp_path / "prom"), "groups": {}},
            "probe_icmp": {"targets_file": str(tmp_path / "icmp.json"), "groups": {}},
            "probe_http": {"targets_file": str(tmp_path / "http.json"), "groups": {}},
            "syslog": {
                "config_file": str(tmp_path / "syslog.conf"),
                "syntax_check": False,
                "groups": {},
            },
        }
    )


class TestRunOnce:
    def test_all_generators_invoked(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_TOKEN", "tok")
        cfg = _full_config(tmp_path)

        mock_client = MagicMock()
        mock_client.get_devices.return_value = []
        mock_client.get_services.return_value = []

        with (
            patch("netbox2prom.__main__.NetBoxClient", return_value=mock_client),
            patch("netbox2prom.__main__.generate_prometheus_configs") as mock_prom,
            patch("netbox2prom.__main__.generate_probe_icmp_targets") as mock_icmp,
            patch("netbox2prom.__main__.generate_probe_http_targets") as mock_http,
            patch("netbox2prom.__main__.generate_syslog_config", return_value=False) as mock_syslog,
            patch("netbox2prom.__main__.reload_services") as mock_reload,
        ):
            run_once(cfg)

            mock_client.get_devices.assert_called_once()
            mock_client.get_services.assert_called_once()
            mock_prom.assert_called_once()
            mock_icmp.assert_called_once()
            mock_http.assert_called_once()
            mock_syslog.assert_called_once()
            mock_reload.assert_called_once()

    def test_only_http_skips_device_fetch(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_TOKEN", "tok")
        monkeypatch.setenv("ENABLE_PROBE_HTTP", "true")
        monkeypatch.setenv("ENABLE_PROMETHEUS", "false")
        monkeypatch.setenv("ENABLE_PROBE_ICMP", "false")
        monkeypatch.setenv("ENABLE_SYSLOG", "false")

        cfg = _full_config(tmp_path)

        mock_client = MagicMock()
        mock_client.get_services.return_value = []

        with (
            patch("netbox2prom.__main__.NetBoxClient", return_value=mock_client),
            patch("netbox2prom.__main__.generate_probe_http_targets"),
            patch("netbox2prom.__main__.reload_services"),
        ):
            run_once(cfg)

            mock_client.get_devices.assert_not_called()
            mock_client.get_services.assert_called_once()

    def test_no_http_skips_service_fetch(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NETBOX_TOKEN", "tok")
        monkeypatch.setenv("ENABLE_PROMETHEUS", "true")
        monkeypatch.setenv("ENABLE_PROBE_HTTP", "false")
        monkeypatch.setenv("ENABLE_PROBE_ICMP", "false")
        monkeypatch.setenv("ENABLE_SYSLOG", "false")

        cfg = Config(
            {
                "netbox": {"url": "https://nb.test", "tag": "mon"},
                "prometheus": {"scrape_dir": str(tmp_path / "prom"), "groups": {}},
            }
        )

        mock_client = MagicMock()
        mock_client.get_devices.return_value = []

        with (
            patch("netbox2prom.__main__.NetBoxClient", return_value=mock_client),
            patch("netbox2prom.__main__.generate_prometheus_configs"),
            patch("netbox2prom.__main__.reload_services"),
        ):
            run_once(cfg)

            mock_client.get_devices.assert_called_once()
            mock_client.get_services.assert_not_called()
