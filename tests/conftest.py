from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _netbox_token_env(monkeypatch):
    """Все тесты требуют NETBOX_TOKEN, даже если не делают реальных запросов."""
    monkeypatch.setenv("NETBOX_TOKEN", "test-token-abc")


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"
