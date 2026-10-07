"""Minimal JSON-Schema subset validator for structured-output contracts.

Model output that merely *looks* like JSON is never trusted: it must parse and
validate. Supports type, enum, required, properties, additionalProperties(false),
items, minimum/maximum, minLength/maxLength.
"""
from __future__ import annotations

import json
from typing import Any

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t]) if t in _TYPES else True


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_is(value, x) for x in types):
            return [f"{path}: expected {'/'.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: not in enum")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                errors.append(f"{path}.{k}: required")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                errors += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{k}: unexpected property")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += validate(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: too long")
    return errors


def parse_and_validate(text: str, schema: dict) -> tuple[Any, list[str]]:
    s = text.strip()
    if s.startswith("```"):  # tolerate a fenced block, nothing fancier
        s = s.strip("`")
        s = s[s.find("\n") + 1:] if "\n" in s else s
        s = s.rsplit("```", 1)[0] if "```" in s else s
    try:
        data = json.loads(s)
    except ValueError:
        return None, ["output is not valid JSON"]
    return data, validate(data, schema)
