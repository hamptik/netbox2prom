"""Tests for the declarative rule engine (conditions.py)."""

from __future__ import annotations

import pytest
from conftest import make_device, make_service

from netbox2prom.conditions import _normalize_list, match_conditions


class TestExactStringMatch:
    def test_matching_string(self) -> None:
        dev = make_device(vendor="cisco")
        assert match_conditions(dev, {"vendor": "cisco"}) is True

    def test_non_matching_string(self) -> None:
        dev = make_device(vendor="juniper")
        assert match_conditions(dev, {"vendor": "cisco"}) is False

    def test_missing_attribute_treated_as_none(self) -> None:
        dev = make_device(vendor=None)
        assert match_conditions(dev, {"vendor": "cisco"}) is False


class TestModelNormalization:
    def test_model_is_case_insensitive(self) -> None:
        dev = make_device(model="Catalyst-9300")
        assert match_conditions(dev, {"model": "catalyst-9300"}) is True

    def test_model_exact_string_lowercased(self) -> None:
        dev = make_device(model="Catalyst-9300")
        assert match_conditions(dev, {"model": "Catalyst-9300"}) is True

    def test_model_non_matching(self) -> None:
        dev = make_device(model="nexus-9000")
        assert match_conditions(dev, {"model": "catalyst-9300"}) is False


class TestListCondition:
    def test_value_in_list(self) -> None:
        dev = make_device(vendor="cisco")
        assert match_conditions(dev, {"vendor": ["cisco", "juniper"]}) is True

    def test_value_not_in_list(self) -> None:
        dev = make_device(vendor="arista")
        assert match_conditions(dev, {"vendor": ["cisco", "juniper"]}) is False

    def test_model_list_is_lowercased(self) -> None:
        dev = make_device(model="Catalyst-9300")
        assert match_conditions(dev, {"model": ["catalyst-9300", "nexus"]}) is True


class TestNotNullCondition:
    def test_not_null_passes_when_value_exists(self) -> None:
        dev = make_device(oob_ip="10.0.0.1")
        assert match_conditions(dev, {"oob_ip": "not_null"}) is True

    def test_not_null_fails_when_none(self) -> None:
        dev = make_device(oob_ip=None)
        assert match_conditions(dev, {"oob_ip": "not_null"}) is False


class TestNullCondition:
    def test_null_passes_when_none(self) -> None:
        dev = make_device(oob_ip=None)
        assert match_conditions(dev, {"oob_ip": None}) is True

    def test_null_fails_when_value_exists(self) -> None:
        dev = make_device(oob_ip="10.0.0.1")
        assert match_conditions(dev, {"oob_ip": None}) is False


class TestAnyExceptCondition:
    def test_matches_when_not_in_exclude_list(self) -> None:
        dev = make_device(vendor="cisco")
        conditions = {"vendor": "any_except", "vendor_exclude": ["juniper", "arista"]}
        assert match_conditions(dev, conditions) is True

    def test_rejects_when_in_exclude_list(self) -> None:
        dev = make_device(vendor="juniper")
        conditions = {"vendor": "any_except", "vendor_exclude": ["juniper", "arista"]}
        assert match_conditions(dev, conditions) is False

    def test_rejects_when_none(self) -> None:
        dev = make_device(vendor=None)
        conditions = {"vendor": "any_except", "vendor_exclude": ["juniper"]}
        assert match_conditions(dev, conditions) is False

    def test_exclude_value_is_lowercased(self) -> None:
        """Value is lowercased before comparison, but exclude list is not."""
        dev = make_device(vendor="Cisco")
        conditions = {"vendor": "any_except", "vendor_exclude": ["cisco"]}
        assert match_conditions(dev, conditions) is False

    def test_model_exclude_is_lowercased(self) -> None:
        dev = make_device(model="Catalyst-9300")
        conditions = {"model": "any_except", "model_exclude": ["CATALYST-9300"]}
        assert match_conditions(dev, conditions) is False

    def test_empty_exclude_matches_anything(self) -> None:
        dev = make_device(vendor="cisco")
        conditions = {"vendor": "any_except"}
        assert match_conditions(dev, conditions) is True


class TestNotInCondition:
    def test_passes_when_not_in_exclude(self) -> None:
        dev = make_device(vendor="cisco")
        conditions = {"vendor": "not_in", "vendor_exclude": ["juniper"]}
        assert match_conditions(dev, conditions) is True

    def test_fails_when_in_exclude(self) -> None:
        dev = make_device(vendor="juniper")
        conditions = {"vendor": "not_in", "vendor_exclude": ["juniper"]}
        assert match_conditions(dev, conditions) is False

    def test_passes_when_none(self) -> None:
        dev = make_device(vendor=None)
        conditions = {"vendor": "not_in", "vendor_exclude": ["juniper"]}
        assert match_conditions(dev, conditions) is True


class TestTagsContains:
    def test_single_tag_string_match(self) -> None:
        dev = make_device(tags=["monitoring", "core"])
        assert match_conditions(dev, {"tags_contains": "monitoring"}) is True

    def test_single_tag_string_no_match(self) -> None:
        dev = make_device(tags=["core"])
        assert match_conditions(dev, {"tags_contains": "monitoring"}) is False

    def test_list_of_tags_any_match(self) -> None:
        dev = make_device(tags=["core"])
        assert match_conditions(dev, {"tags_contains": ["monitoring", "core"]}) is True

    def test_list_of_tags_no_match(self) -> None:
        dev = make_device(tags=["edge"])
        assert match_conditions(dev, {"tags_contains": ["monitoring", "core"]}) is False

    def test_empty_device_tags(self) -> None:
        dev = make_device(tags=[])
        assert match_conditions(dev, {"tags_contains": "monitoring"}) is False


class TestMultipleConditions:
    def test_all_conditions_must_match(self) -> None:
        dev = make_device(vendor="cisco", role="router", tags=["core"])
        conditions = {
            "vendor": "cisco",
            "role": "router",
            "tags_contains": "core",
        }
        assert match_conditions(dev, conditions) is True

    def test_one_failing_condition_rejects(self) -> None:
        dev = make_device(vendor="cisco", role="switch", tags=["core"])
        conditions = {
            "vendor": "cisco",
            "role": "router",
            "tags_contains": "core",
        }
        assert match_conditions(dev, conditions) is False

    def test_exclude_key_is_skipped(self) -> None:
        dev = make_device(vendor="cisco")
        conditions = {"vendor_exclude": ["juniper"]}
        assert match_conditions(dev, conditions) is True


class TestEmptyConditions:
    def test_empty_conditions_matches_all(self) -> None:
        dev = make_device()
        assert match_conditions(dev, {}) is True


class TestServiceConditions:
    def test_service_protocol_match(self) -> None:
        svc = make_service(protocol="tcp")
        assert match_conditions(svc, {"protocol": "tcp"}) is True

    def test_service_tags_contains(self) -> None:
        svc = make_service(tags=["web", "prod"])
        assert match_conditions(svc, {"tags_contains": ["web"]}) is True


class TestNormalizeList:
    def test_model_field_lowercases(self) -> None:
        assert _normalize_list(["Catalyst", "NEXUS"], "model") == ["catalyst", "nexus"]

    def test_non_model_field_preserves_case(self) -> None:
        assert _normalize_list(["Cisco", "Juniper"], "vendor") == ["Cisco", "Juniper"]

    def test_string_values(self) -> None:
        assert _normalize_list([1, 2, 3], "vendor") == ["1", "2", "3"]


@pytest.mark.parametrize(
    ("conditions", "should_match"),
    [
        ({"vendor": "cisco"}, True),
        ({"vendor": "juniper"}, False),
        ({"vendor": ["cisco", "juniper"]}, True),
        ({"vendor": "not_null"}, True),
        ({"oob_ip": "not_null"}, True),
        ({"oob_ip": None}, False),
        ({"nonexistent": "value"}, False),
    ],
)
def test_parametrized_conditions(conditions: dict, should_match: bool) -> None:
    dev = make_device(vendor="cisco", oob_ip="10.0.0.1")
    assert match_conditions(dev, conditions) is should_match
