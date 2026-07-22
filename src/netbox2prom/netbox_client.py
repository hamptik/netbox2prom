from __future__ import annotations

import logging
from typing import Any

import pynetbox
import requests
from pynetbox.core.query import RequestError

from .config import Config
from .models import Device, IpAddress, Service

logger = logging.getLogger(__name__)


class NetBoxError(RuntimeError):
    """Raised when NetBox returns an unrecoverable error."""


class _TimeoutSession(requests.Session):
    """``requests.Session`` that injects a default per-request timeout.

    ``pynetbox`` does not expose a ``timeout`` argument on its API object,
    and ``requests`` itself defaults to no timeout (i.e. waits forever).
    Mounting this session on ``api.http_session`` guarantees every HTTP
    call made by ``pynetbox`` is bounded by ``timeout``.
    """

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__()
        self._timeout = timeout

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        kwargs.setdefault("timeout", self._timeout)
        return super().request(method, url, *args, **kwargs)


class NetBoxClient:
    """Thin wrapper over ``pynetbox.api``.

    The wrapper:
      * configures authentication, timeouts and the ``tag`` filter;
      * uses ``limit``-based pagination so result sets larger than the
        server-side ``MAX_PAGE_SIZE`` are not silently truncated;
      * converts every ``Record`` returned by ``pynetbox`` back to a plain
        ``dict`` so the existing ``from_netbox(dict)`` factories in
        :mod:`netbox2prom.models` keep working unchanged;
      * wraps ``pynetbox`` exceptions in :class:`NetBoxError` so callers do
        not need to import ``pynetbox`` themselves.
    """

    def __init__(self, config: Config) -> None:
        self._tag = config.netbox_tag or None
        self._page_size = config.netbox_page_size

        session = _TimeoutSession(timeout=config.netbox_timeout)
        session.headers.update({"Accept": "application/json"})

        try:
            self._api = pynetbox.api(
                config.netbox_url,
                token=config.netbox_token,
            )
            self._api.http_session = session
        except RequestError as exc:
            raise NetBoxError(f"Failed to initialise NetBox client: {exc}") from exc

    def _filter_kwargs(self) -> dict[str, Any]:
        # ``limit`` is the page size for offset pagination; with the default
        # value of 0 pynetbox asks NetBox for everything in a single shot,
        # which is silently truncated when the deployment enforces
        # ``MAX_PAGE_SIZE``. Passing a positive page size forces proper
        # pagination through the full result set.
        kwargs: dict[str, Any] = {"limit": self._page_size}
        if self._tag:
            kwargs["tag"] = self._tag
        return kwargs

    def _list(self, endpoint: Any) -> list[dict[str, Any]]:
        try:
            return [dict(record) for record in endpoint.filter(**self._filter_kwargs())]
        except RequestError as exc:
            raise NetBoxError(f"Failed to fetch from NetBox: {exc}") from exc

    def get_devices(self) -> list[Device]:
        raw_physical = self._list(self._api.dcim.devices)
        raw_virtual = self._list(self._api.virtualization.virtual_machines)
        logger.info(
            "Fetched %d physical and %d virtual devices",
            len(raw_physical),
            len(raw_virtual),
        )
        return [Device.from_netbox(d) for d in raw_physical + raw_virtual]

    def get_services(self, website_field: str = "website") -> list[Service]:
        raw_services = self._list(self._api.ipam.services)
        services = [
            Service.from_netbox(s, website_field=website_field)
            for s in raw_services
        ]
        with_website = sum(1 for s in services if s.website)
        with_ports = sum(
            1 for s in services if not s.website and s.ports and s.ipaddresses
        )
        logger.info(
            "Fetched %d services (%d with %s field, %d TCP/port targets)",
            len(raw_services),
            with_website,
            website_field,
            with_ports,
        )
        return services

    def get_ip_addresses(self) -> list[IpAddress]:
        raw = self._list(self._api.ipam.ip_addresses)
        result = [IpAddress.from_netbox(ip) for ip in raw]
        logger.info("Fetched %d IP addresses", len(result))
        return result
