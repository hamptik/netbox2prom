from __future__ import annotations

import json
from pathlib import Path

import pytest
import responses

from netbox2prom.config import Config
from netbox2prom.netbox_client import NetBoxClient, NetBoxError

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _make_config(url: str = "https://netbox.example.net") -> Config:
    return Config({
        "netbox": {
            "url": url,
            "tag": "monitoring",
            "timeout": 5,
            "page_size": 50,
        }
    })


def _page(results, next_url=None, count=None):
    return {
        "count": count if count is not None else len(results),
        "next": next_url,
        "previous": None,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

@responses.activate
def test_client_does_not_call_api_on_init():
    # Конструктор не должен делать HTTP-запросов; pynetbox ленивый.
    client = NetBoxClient(_make_config())
    assert len(responses.calls) == 0
    assert client is not None


# ---------------------------------------------------------------------------
# get_devices
# ---------------------------------------------------------------------------

@responses.activate
def test_get_devices_combines_physical_and_virtual():
    phys = _load("device_physical.json")
    vm = _load("device_virtual.json")

    responses.add(
        responses.GET,
        "https://netbox.example.net/api/dcim/devices/",
        json=_page([phys]),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/virtualization/virtual-machines/",
        json=_page([vm]),
        status=200,
    )

    devices = NetBoxClient(_make_config()).get_devices()
    assert len(devices) == 2
    assert {d.name for d in devices} == {"device-01", "vm-app-01"}
    # page_size должен передаваться как limit= чтобы пагинация была safe
    sent = [c.request.url for c in responses.calls]
    assert all("limit=50" in u for u in sent)
    assert all("tag=monitoring" in u for u in sent)


@responses.activate
def test_get_devices_paginates_when_more_than_one_page():
    phys = _load("device_physical.json")

    responses.add(
        responses.GET,
        "https://netbox.example.net/api/dcim/devices/",
        json=_page([phys], next_url="https://netbox.example.net/api/dcim/devices/?limit=50&offset=50", count=2),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/dcim/devices/",
        json=_page([phys], count=2),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/virtualization/virtual-machines/",
        json=_page([]),
        status=200,
    )

    devices = NetBoxClient(_make_config()).get_devices()
    assert len(devices) == 2  # две страницы по одной записи


@responses.activate
def test_get_devices_wraps_request_error_as_netbox_error():
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/dcim/devices/",
        json={"detail": "Authentication credentials were not provided."},
        status=403,
    )

    with pytest.raises(NetBoxError):
        NetBoxClient(_make_config()).get_devices()


@responses.activate
def test_get_devices_no_tag_omits_tag_param():
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/dcim/devices/",
        json=_page([]),
        status=200,
    )
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/virtualization/virtual-machines/",
        json=_page([]),
        status=200,
    )

    cfg = Config({"netbox": {"url": "https://netbox.example.net", "tag": "", "timeout": 5, "page_size": 50}})
    NetBoxClient(cfg).get_devices()
    sent = [c.request.url for c in responses.calls]
    assert all("tag=" not in u for u in sent), sent
    assert all("limit=50" in u for u in sent), sent


# ---------------------------------------------------------------------------
# get_services
# ---------------------------------------------------------------------------

@responses.activate
def test_get_services_extracts_device_name_in_42_and_46_format():
    s42 = _load("service_42_vm_parent.json")
    s46 = _load("service_46_parent_vm.json")
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/ipam/services/",
        json=_page([s42, s46]),
        status=200,
    )

    services = NetBoxClient(_make_config()).get_services()
    assert len(services) == 2
    assert services[0].device_name == "vm-app-01"
    assert services[1].device_name == "vm-app-01"  # same name via parent


@responses.activate
def test_get_services_counts_website_and_tcp_targets():
    with_website = _load("service_42_vm_parent.json")          # website set
    tcp_target = _load("service_46_parent_device.json")        # ports + ip, no website
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/ipam/services/",
        json=_page([with_website, tcp_target]),
        status=200,
    )

    services = NetBoxClient(_make_config()).get_services()
    assert len(services) == 2


# ---------------------------------------------------------------------------
# get_ip_addresses
# ---------------------------------------------------------------------------

@responses.activate
def test_get_ip_addresses_handles_dcim_and_vminterface():
    dcim_ip = _load("ipaddr_dcim_interface.json")
    vm_ip = _load("ipaddr_vminterface.json")
    responses.add(
        responses.GET,
        "https://netbox.example.net/api/ipam/ip-addresses/",
        json=_page([dcim_ip, vm_ip]),
        status=200,
    )

    ips = NetBoxClient(_make_config()).get_ip_addresses()
    assert len(ips) == 2
    assert ips[0].device_name == "device-01"
    assert ips[0].virtual is False
    assert ips[1].device_name == "vm-app-01"
    assert ips[1].virtual is True


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

def test_timeout_session_injects_default_timeout():
    """_TimeoutSession проставляет дефолтный timeout на каждый запрос."""
    from netbox2prom.netbox_client import _TimeoutSession

    captured = {}

    class FakeAdapter:
        def send(self, request, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            raise RuntimeError("stop")

    sess = _TimeoutSession(timeout=7)
    sess.mount("https://", FakeAdapter())
    sess.mount("http://", FakeAdapter())

    with pytest.raises(RuntimeError):
        sess.get("https://x.example/")

    assert captured["timeout"] == 7


def test_timeout_session_does_not_override_explicit_timeout():
    from netbox2prom.netbox_client import _TimeoutSession

    captured = {}

    class FakeAdapter:
        def send(self, request, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            raise RuntimeError("stop")

    sess = _TimeoutSession(timeout=7)
    sess.mount("https://", FakeAdapter())

    with pytest.raises(RuntimeError):
        sess.get("https://x.example/", timeout=30)

    assert captured["timeout"] == 30
