from __future__ import annotations

import logging

import requests

from .config import Config
from .models import Device, Service

logger = logging.getLogger(__name__)


class NetBoxClient:
    def __init__(self, config: Config):
        self._url = config.netbox_url
        self._token = config.netbox_token
        self._tag = config.netbox_tag
        self._endpoints = config.netbox_endpoints
        self._timeout = config.netbox_timeout
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Token {self._token}",
                "Accept": "application/json",
            })
        return self._session

    def _fetch_all(self, endpoint: str, params: dict | None = None) -> list[dict]:
        results: list[dict] = []
        url = f"{self._url.rstrip('/')}{endpoint}"
        query = params
        while url:
            r = self.session.get(url, params=query, timeout=self._timeout)
            if not r.ok:
                logger.error("NetBox API %s -> HTTP %d: %s", r.url, r.status_code, r.text[:500])
                r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            url = data.get("next")
            query = None
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
        services = [s for s in services if s.website]
        logger.info(
            "Fetched %d services (%d with %s field)",
            len(raw_services),
            len(services),
            website_field,
        )
        return services
