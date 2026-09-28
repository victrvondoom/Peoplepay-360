"""JSON parsing utility for agent outputs."""

from __future__ import annotations

import ast
import json
import re


def _strip_trailing_commas(text: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", text)


def _insert_missing_commas(text: str) -> str:
    """When a string value spans many lines (a full drafted letter), the
    model frequently forgets the comma that should separate it from the
    next "key": pair -- valid-looking multi-line JSON that's actually just
    several fields silently mashed together with no separator. Detect a
    closing quote followed by only whitespace/newlines and then another
    quoted key, and insert the missing comma."""
    return re.sub(r'"(\s*\n\s*)"([a-zA-Z_][a-zA-Z0-9_]*)":', r'",\1"\2":', text)


def _python_literal_repair(text: str) -> dict | None:
    """Smaller LLMs sometimes emit Python-dict style instead of strict JSON
    (single-quoted keys/values, unquoted True/False/None) -- that's invalid
    JSON but valid-ish Python, so a literal_eval pass recovers it instead of
    falling through to dumping the raw text into the UI."""
    pyish = re.sub(r"\btrue\b", "True", text)
    pyish = re.sub(r"\bfalse\b", "False", pyish)
    pyish = re.sub(r"\bnull\b", "None", pyish)
    try:
        value = ast.literal_eval(pyish)
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, dict) else None


def parse_agent_json(raw: str, fallback_fields: dict | None = None) -> dict:
    """Parse JSON from LLM output, handling markdown fences and common issues."""
    text = raw.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    candidates = [text]
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(0))

    for candidate in list(candidates):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # strict=False allows raw control characters (literal newlines,
        # tabs) inside string values -- the model routinely writes a
        # numbered plan as "1. ...\n2. ...\n3. ..." with real newlines
        # instead of the \n escape JSON requires, which strict mode
        # rejects outright with "Invalid control character".
        try:
            return json.loads(candidate, strict=False)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_strip_trailing_commas(candidate), strict=False)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_insert_missing_commas(candidate), strict=False)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(_strip_trailing_commas(_insert_missing_commas(candidate)), strict=False)
        except json.JSONDecodeError:
            pass
        repaired = _python_literal_repair(candidate)
        if repaired is not None:
            return repaired

    # Fallback: return the raw text in a summary field
    result = {"summary": text, "_parse_failed": True}
    if fallback_fields:
        for key, default in fallback_fields.items():
            result.setdefault(key, default)
    return result


def unwrap_nested_json_summary(value: str, fallback: str = "") -> str:
    """The model occasionally re-emits its own full JSON output a second
    time as the *value* of the "summary" field, instead of a plain prose
    sentence -- the outer parse_agent_json() call still succeeds either way
    (the outer JSON is well-formed), so this isn't caught by any parse
    failure path; it just silently leaks a literal '{"can_appeal": "YES",
    ...}' blob straight into what the user reads as the case summary/
    strategy/answer text. If the value looks like a JSON object, try to pull
    a real prose field back out of it. That nested blob is itself often cut
    off mid-string by the same [:2000] truncation applied to the outer raw
    text (the model started re-emitting a full duplicate response and ran
    out of the truncation budget partway through), which makes it
    unparseable with no complete data to recover -- in that case fall back
    to the caller-supplied already-good field (e.g. recommended_strategy)
    instead of leaking the broken, truncated JSON fragment verbatim."""
    stripped = value.strip()
    if not stripped.startswith("{"):
        return value
    # Deliberately not also requiring stripped.endswith("}") here -- a
    # truncated nested blob (see docstring) won't end cleanly either, and
    # that's exactly the case that most needs the fallback below.
    nested = parse_agent_json(stripped)
    if isinstance(nested, dict) and not nested.get("_parse_failed"):
        for key in ("summary", "recommended_strategy", "answer"):
            nested_value = nested.get(key)
            if isinstance(nested_value, str) and nested_value.strip() and not nested_value.strip().startswith("{"):
                return nested_value
    return fallback or value
