from __future__ import annotations

from typing import Union

from .models import Device, Service


def match_conditions(obj: Union[Device, Service], conditions: dict) -> bool:
    for key, cond in conditions.items():
        if key.endswith("_exclude"):
            continue

        if key == "tags_contains":
            tag_list = cond if isinstance(cond, list) else [cond]
            if not any(tag in tag_list for tag in obj.tags):
                return False
            continue

        val = getattr(obj, key, None)
        if key == "model" and val:
            val = val.lower()

        if cond is None:
            if val is not None:
                return False
        elif cond == "not_null":
            if val is None:
                return False
        elif cond == "any_except":
            if val is None:
                return False
            exclude_key = f"{key}_exclude"
            exclude_list = conditions.get(exclude_key, [])
            normalized_exclude = _normalize_list(exclude_list, key)
            if str(val).lower() in normalized_exclude:
                return False
        elif cond == "not_in":
            exclude_key = f"{key}_exclude"
            exclude_list = conditions.get(exclude_key, [])
            normalized_exclude = _normalize_list(exclude_list, key)
            if val is not None and str(val).lower() in normalized_exclude:
                return False
        elif isinstance(cond, list):
            normalized_cond = _normalize_list(cond, key)
            if str(val).lower() not in normalized_cond:
                return False
        else:
            if key == "model":
                if str(val).lower() != str(cond).lower():
                    return False
            else:
                if str(val) != str(cond):
                    return False

    return True


def _normalize_list(values: list, field_name: str) -> list[str]:
    if field_name == "model":
        return [str(v).lower() for v in values]
    return [str(v) for v in values]
