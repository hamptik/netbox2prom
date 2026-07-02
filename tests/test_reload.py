"""Tests for service reload logic (reload.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from netbox2prom.config import Config
from netbox2prom.reload import reload_http, reload_services


class TestReloadHttp:
    @patch("netbox2prom.reload.requests.post")
    def test_success(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        reload_http("http://prom:9090", "prometheus")
        mock_post.assert_called_once_with("http://prom:9090/-/reload", timeout=30)

    @patch("netbox2prom.reload.requests.post")
    def test_non_200_logs_warning(self, mock_post: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        reload_http("http://prom:9090", "prometheus")
        # No exception raised — just a warning log
        mock_post.assert_called_once()

    @patch("netbox2prom.reload.requests.post")
    def test_exception_logged(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = ConnectionError("refused")

        reload_http("http://prom:9090", "prometheus")
        # No exception propagated — just logged
        mock_post.assert_called_once()


class TestReloadServices:
    def test_deduplicates_addresses(self) -> None:
        """When probe_icmp and probe_http share the same reload address,
        only one HTTP POST should be sent."""
        cfg = Config(
            {
                "probe_icmp": {"reload_address": "http://alloy:12345"},
                "probe_http": {"reload_address": "http://alloy:12345"},
                "prometheus": {"reload_address": "http://prom:9090"},
            }
        )

        with (
            patch("netbox2prom.reload.reload_http") as mock_http,
            patch("netbox2prom.reload.reload_syslog") as mock_syslog,
        ):
            reload_services(
                cfg,
                enabled={"probe_icmp", "probe_http", "prometheus"},
                syslog_changed=False,
            )

            # Two unique addresses: alloy + prometheus
            assert mock_http.call_count == 2
            addresses = sorted(str(call.args[0]) for call in mock_http.call_args_list)
            assert "http://alloy:12345" in addresses
            assert "http://prom:9090" in addresses
            mock_syslog.assert_not_called()

    def test_syslog_reloaded_when_changed(self) -> None:
        cfg = Config({"syslog": {"config_file": "/tmp/syslog.conf"}})

        with (
            patch("netbox2prom.reload.reload_http") as mock_http,
            patch("netbox2prom.reload.reload_syslog") as mock_syslog,
        ):
            reload_services(cfg, enabled={"syslog"}, syslog_changed=True)

            mock_http.assert_not_called()
            mock_syslog.assert_called_once_with({"config_file": "/tmp/syslog.conf"})

    def test_syslog_not_reloaded_when_unchanged(self) -> None:
        cfg = Config({"syslog": {"config_file": "/tmp/syslog.conf"}})

        with (
            patch("netbox2prom.reload.reload_http"),
            patch("netbox2prom.reload.reload_syslog") as mock_syslog,
        ):
            reload_services(cfg, enabled={"syslog"}, syslog_changed=False)

            mock_syslog.assert_not_called()

    def test_empty_reload_address_skipped(self) -> None:
        cfg = Config(
            {
                "prometheus": {"reload_address": ""},
            }
        )

        with patch("netbox2prom.reload.reload_http") as mock_http:
            reload_services(cfg, enabled={"prometheus"}, syslog_changed=False)

            mock_http.assert_not_called()

    def test_shared_address_label_joined(self) -> None:
        cfg = Config(
            {
                "probe_icmp": {"reload_address": "http://alloy:12345"},
                "probe_http": {"reload_address": "http://alloy:12345"},
            }
        )

        with (
            patch("netbox2prom.reload.reload_http") as mock_http,
            patch("netbox2prom.reload.reload_syslog"),
        ):
            reload_services(
                cfg,
                enabled={"probe_icmp", "probe_http"},
                syslog_changed=False,
            )

            assert mock_http.call_count == 1
            label = mock_http.call_args.args[1]
            assert "probe_icmp" in label
            assert "probe_http" in label
