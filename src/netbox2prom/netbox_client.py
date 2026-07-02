from __future__ import annotations

import logging
from typing import Any

import requests

from .config import Config
from .models import Device, Service

logger = logging.getLogger(__name__)


class NetBoxError(RuntimeError):
    """Raised when NetBox returns an unrecoverable error."""


class NetBoxClient:
    def __init__(self, config: Config) -> None:
        self._url = config.netbox_url.rstrip("/")
        self._token = config.netbox_token
        self._tag = config.netbox_tag
        self._endpoints = config.netbox_endpoints
        self._timeout = config.netbox_timeout
        self._page_size = config.netbox_page_size
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {self._token}",
            "Accept": "application/json",
        })

    def _fetch_all(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch the full result list of a paged NetBox endpoint.

        Pagination is driven by ``offset`` against ``page_size`` rather than the
        ``limit=0`` shortcut: when a NetBox deployment sets ``MAX_PAGE_SIZE`` the
        server silently caps any request (including ``limit=0``), so a single
        shot would drop everything beyond that cap. Walking the pages by offset
        guarantees the complete result set is retrieved regardless of the
        server-side limit.
        """
        base_params: dict[str, Any] = dict(params or {})
        base_params["limit"] = self._page_size
        url = f"{self._url}{endpoint}"

        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            request_params = dict(base_params)
            request_params["offset"] = offset
            try:
                resp = self._session.get(
                    url, params=request_params, timeout=self._timeout
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                raise NetBoxError(f"Failed to fetch {endpoint}: {exc}") from exc

            payload = resp.json()
            # Non-paged endpoints return a bare list; return it as-is.
            if isinstance(payload, list):
                return payload

            page = list(payload.get("results", []))
            results.extend(page)

            # Stop on the last page: an empty page, a short page, or when the
            # accumulated offset reaches the reported total count.
            if not page or len(page) < self._page_size:
                break
            total = payload.get("count")
            if isinstance(total, int) and offset + len(page) >= total:
                break
            offset += len(page)

        return results

    def get_devices(self) -> list[Device]:
        params = {"tag": self._tag} if self._tag else None
        raw_physical = self._fetch_all(self._endpoints["devices"], params)
        raw_virtual = self._fetch_all(self._endpoints["virtual_machines"], params)
        logger.info(
            "Fetched %d physical and %d virtual devices",
            len(raw_physical),
            len(raw_virtual),
        )
        return [Device.from_netbox(d) for d in raw_physical + raw_virtual]

    def get_services(self, website_field: str = "website") -> list[Service]:
        params = {"tag": self._tag} if self._tag else None
        raw_services = self._fetch_all(self._endpoints["services"], params)
        services = [
            Service.from_netbox(s, website_field=website_field)
            for s in raw_services
        ]
        with_website = sum(1 for s in services if s.website)
        with_ports = sum(1 for s in services if not s.website and s.ports and s.ipaddresses)
        logger.info(
            "Fetched %d services (%d with %s field, %d TCP/port targets)",
            len(raw_services),
            with_website,
            website_field,
            with_ports,
        )
        return services
