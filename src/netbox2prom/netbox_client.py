from __future__ import annotations

import logging

import requests

from .config import Config
from .models import Device

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

    def _fetch_all(self, path: str) -> list[dict]:
        results: list[dict] = []
        next_url = path
        while next_url:
            if next_url.startswith("http"):
                full_url = next_url
            else:
                full_url = f"{self._url.rstrip('/')}{next_url}"
            r = self.session.get(full_url, timeout=self._timeout)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("results", []))
            next_url = data.get("next")
            if next_url and next_url.startswith(self._url):
                next_url = next_url[len(self._url):]
        return results

    def get_devices(self) -> list[Device]:
        tag_filter = f"?tag={self._tag}" if self._tag else ""
        raw_physical = self._fetch_all(f"{self._endpoints['devices']}{tag_filter}")
        raw_virtual = self._fetch_all(f"{self._endpoints['virtual_machines']}{tag_filter}")
        logger.info(
            "Fetched %d physical and %d virtual devices",
            len(raw_physical),
            len(raw_virtual),
        )
        return [Device.from_netbox(d) for d in raw_physical + raw_virtual]
