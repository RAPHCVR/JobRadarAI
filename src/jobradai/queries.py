from __future__ import annotations

import re
from typing import Any

from jobradai.text import normalize_space


_EARLY_QUERY_RE = re.compile(
    r"\b(graduate|new grad|early careers?|campus|trainee|entry[- ]level|junior)\b",
    re.IGNORECASE,
)


def select_query_items(
    config: dict[str, Any],
    *,
    limit: int | None = None,
    early_career_min: int = 0,
) -> list[dict[str, Any]]:
    rows = _query_items(config)
    rows.sort(key=lambda item: (-float(item.get("priority") or 0), int(item["_index"])))
    if limit is None or limit <= 0 or len(rows) <= limit:
        return [_public_item(item) for item in rows]

    selected = rows[:limit]
    selected_terms = {str(item["term"]).lower() for item in selected}
    early_rows = [item for item in rows if _is_early_item(item)]
    missing_early = [item for item in early_rows if str(item["term"]).lower() not in selected_terms]
    target_early = min(max(0, early_career_min), len(early_rows), limit)
    while _count_early(selected) < target_early and missing_early:
        candidate = missing_early.pop(0)
        replacement_index = _replacement_index(selected)
        if replacement_index is None:
            break
        selected[replacement_index] = candidate
        selected.sort(key=lambda item: (-float(item.get("priority") or 0), int(item["_index"])))
    return [_public_item(item) for item in selected]


def select_query_terms(
    config: dict[str, Any],
    *,
    limit: int | None = None,
    early_career_min: int = 0,
) -> list[str]:
    return [item["term"] for item in select_query_items(config, limit=limit, early_career_min=early_career_min)]


def _query_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(config.get("queries", [])):
        if not isinstance(item, dict):
            continue
        term = normalize_space(str(item.get("term") or ""))
        if not term:
            continue
        rows.append(
            {
                "term": term,
                "priority": _float(item.get("priority"), 0.0),
                "category": normalize_space(str(item.get("category") or "")) or _infer_category(term),
                "_index": index,
            }
        )
    return rows


def _infer_category(term: str) -> str:
    return "early_career" if _EARLY_QUERY_RE.search(term) else "core"


def _is_early_item(item: dict[str, Any]) -> bool:
    return str(item.get("category") or "") in {"early_career", "graduate"} or _EARLY_QUERY_RE.search(str(item.get("term") or "")) is not None


def _count_early(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if _is_early_item(item))


def _replacement_index(items: list[dict[str, Any]]) -> int | None:
    candidates = [
        (float(item.get("priority") or 0), int(item.get("_index") or 0), index)
        for index, item in enumerate(items)
        if not _is_early_item(item)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (row[0], -row[1]))[0][2]


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
