"""Tests for NetBoxClient, focused on pagination (netbox_client.py).

Uses the hand-written FakeSession pattern from netbox2mapgl.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests
from conftest import FakeResponse, FakeSession

from netbox2prom.config import Config
from netbox2prom.netbox_client import NetBoxClient, NetBoxError


def _config(
    monkeypatch: pytest.MonkeyPatch,
    *,
    page_size: int = 50,
    tag: str = "monitoring",
    url: str = "https://nb.example.com",
    timeout: int = 10,
) -> Config:
    monkeypatch.setenv("NETBOX_TOKEN", "tok")
    return Config(
        {
            "netbox": {
                "url": url,
                "tag": tag,
                "page_size": page_size,
                "timeout": timeout,
            },
        }
    )


def _wire(client: NetBoxClient, pages: list[Any]) -> FakeSession:
    """Replace client._session with a FakeSession holding scripted pages."""
    fake = FakeSession(pages)
    client._session = fake  # type: ignore[assignment]
    return fake


def _make_client(config: Config) -> NetBoxClient:
    return NetBoxClient(config)


# ---------------------------------------------------------------------------
# _fetch_all pagination
# ---------------------------------------------------------------------------


class TestFetchAllPagination:
    def test_multi_page_offset_walk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch, page_size=2)
        client = _make_client(cfg)
        fake = _wire(
            client,
            [
                {"count": 5, "results": [{"id": 1}, {"id": 2}]},
                {"count": 5, "results": [{"id": 3}, {"id": 4}]},
                {"count": 5, "results": [{"id": 5}]},
            ],
        )

        result = client._fetch_all("/api/dcim/devices/", params={"tag": "monitoring"})

        assert [r["id"] for r in result] == [1, 2, 3, 4, 5]
        offsets = [c[1]["offset"] for c in fake.calls]
        assert offsets == [0, 2, 4]
        assert all(c[1]["limit"] == 2 for c in fake.calls)
        # params preserved
        assert all(c[1]["tag"] == "monitoring" for c in fake.calls)

    def test_single_page_stops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch, page_size=50)
        client = _make_client(cfg)
        fake = _wire(client, [{"count": 2, "results": [{"id": 1}, {"id": 2}]}])

        result = client._fetch_all("/api/things/")

        assert result == [{"id": 1}, {"id": 2}]
        assert len(fake.calls) == 1

    def test_empty_result_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch)
        client = _make_client(cfg)
        fake = _wire(client, [{"count": 0, "results": []}])

        assert client._fetch_all("/api/things/") == []
        assert len(fake.calls) == 1

    def test_bare_list_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch)
        client = _make_client(cfg)
        fake = _wire(client, [[{"id": 1}, {"id": 2}]])

        result = client._fetch_all("/api/unpaged/")
        assert result == [{"id": 1}, {"id": 2}]
        assert len(fake.calls) == 1

    def test_stops_on_count_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When offset + page length >= count, pagination stops."""
        cfg = _config(monkeypatch, page_size=3)
        client = _make_client(cfg)
        fake = _wire(
            client,
            [
                {"count": 3, "results": [{"id": 1}, {"id": 2}, {"id": 3}]},
            ],
        )

        result = client._fetch_all("/api/things/")
        assert len(result) == 3
        assert len(fake.calls) == 1

    def test_http_error_raises_netbox_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch)
        client = _make_client(cfg)

        class _ErrorSession:
            def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
                return FakeResponse({}, status=500)

        client._session = _ErrorSession()  # type: ignore[assignment]

        with pytest.raises(NetBoxError, match="Failed to fetch"):
            client._fetch_all("/api/things/")

    def test_connection_error_raises_netbox_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch)
        client = _make_client(cfg)

        class _ConnErrorSession:
            def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
                raise requests.ConnectionError("refused")

        client._session = _ConnErrorSession()  # type: ignore[assignment]

        with pytest.raises(NetBoxError):
            client._fetch_all("/api/things/")


# ---------------------------------------------------------------------------
# get_devices
# ---------------------------------------------------------------------------


class TestGetDevices:
    def test_fetches_physical_and_virtual(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch, page_size=50)
        client = _make_client(cfg)

        from conftest import nb_device

        physical = nb_device(name="rtr1", primary_ip="10.0.0.1/24")
        virtual = nb_device(name="vm1", primary_ip="10.0.0.2/24", vcpus=2)

        pages = [
            {"count": 1, "results": [physical]},  # devices endpoint
            {"count": 1, "results": [virtual]},  # virtual_machines endpoint
        ]
        fake = _wire(client, pages)

        devices = client.get_devices()

        assert len(devices) == 2
        assert devices[0].name == "rtr1"
        assert devices[0].virtual is False
        assert devices[1].name == "vm1"
        assert devices[1].virtual is True
        # Tag param passed through
        assert all(c[1].get("tag") == "monitoring" for c in fake.calls)
        assert "/api/dcim/devices/" in fake.calls[0][0]
        assert "/api/virtualization/virtual-machines/" in fake.calls[1][0]

    def test_empty_tag_omits_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch, tag="")
        client = _make_client(cfg)
        fake = _wire(
            client,
            [
                {"count": 0, "results": []},
                {"count": 0, "results": []},
            ],
        )

        client.get_devices()

        assert "tag" not in fake.calls[0][1]


# ---------------------------------------------------------------------------
# get_services
# ---------------------------------------------------------------------------


class TestGetServices:
    def test_filters_services_without_website(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch, page_size=50)
        client = _make_client(cfg)

        from conftest import nb_service

        with_site = nb_service(name="web", website="https://app.example.com")
        without_site = nb_service(name="ssh", website=None)

        _wire(
            client,
            [
                {"count": 2, "results": [with_site, without_site]},
            ],
        )

        services = client.get_services()
        assert len(services) == 1
        assert services[0].name == "web"
        assert services[0].website == "https://app.example.com"

    def test_custom_website_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _config(monkeypatch)
        client = _make_client(cfg)

        from conftest import nb_service

        svc_data = nb_service(
            name="web", website="https://app.example.com", website_field="custom_url"
        )
        _wire(client, [{"count": 1, "results": [svc_data]}])

        services = client.get_services(website_field="custom_url")
        assert len(services) == 1
        assert services[0].website == "https://app.example.com"
