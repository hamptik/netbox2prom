"""Tests for setup_logging (log.py)."""

from __future__ import annotations

import logging

from netbox2prom.log import setup_logging


def _reset_root_logger() -> None:
    """Clear handlers so basicConfig actually reconfigures the root logger."""
    root = logging.getLogger()
    root.handlers.clear()
    root.level = logging.WARNING


def test_setup_logging_info() -> None:
    _reset_root_logger()
    setup_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_debug() -> None:
    _reset_root_logger()
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_invalid_falls_back_to_info() -> None:
    _reset_root_logger()
    setup_logging("BOGUS")
    assert logging.getLogger().level == logging.INFO
