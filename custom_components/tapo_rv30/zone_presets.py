"""Validation and lookup helpers for integration-owned cleaning-zone presets."""
from __future__ import annotations

from typing import Any

MAX_PRESETS = 100
MAX_ZONES = 20
MAX_COORDINATE_MM = 2_000_000
MAX_NAME_LENGTH = 80


def normalize_zones(raw: Any) -> list[list[int]]:
    """Validate and normalize [x1, y1, x2, y2] rectangles in map millimetres."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_ZONES:
        raise ValueError(f"zones must contain 1 to {MAX_ZONES} rectangles")
    zones = []
    for zone in raw:
        if not isinstance(zone, (list, tuple)) or len(zone) != 4:
            raise ValueError("each zone must be [x1, y1, x2, y2]")
        if any(isinstance(v, bool) for v in zone):
            raise ValueError("zone coordinates must be integers")
        try:
            coords = [int(v) for v in zone]
        except (TypeError, ValueError, OverflowError):
            raise ValueError("zone coordinates must be integers") from None
        if any(str(v).strip() not in (str(i), f"+{i}") for v, i in zip(zone, coords)):
            raise ValueError("zone coordinates must be integers")
        if any(abs(v) > MAX_COORDINATE_MM for v in coords):
            raise ValueError(f"zone coordinates must be within ±{MAX_COORDINATE_MM} mm")
        x1, y1, x2, y2 = coords
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if left == right or top == bottom:
            raise ValueError("zone rectangles must have non-zero width and height")
        zones.append([left, top, right, bottom])
    return zones


def clean_presets(raw: Any) -> list[dict[str, Any]]:
    """Return valid persisted presets, ignoring malformed or obsolete entries."""
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:MAX_PRESETS]:
        if not isinstance(item, dict):
            continue
        preset_id, name = item.get("id"), item.get("name")
        try:
            map_id = int(item.get("map_id"))
            zones = normalize_zones(item.get("zones"))
        except (TypeError, ValueError):
            continue
        if not isinstance(preset_id, str) or not preset_id or not isinstance(name, str):
            continue
        name = name.strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            continue
        out.append({"id": preset_id, "name": name, "map_id": map_id,
                    "map_name": str(item.get("map_name") or ""), "zones": zones})
    return out


def find_preset(presets: list[dict[str, Any]], ref: Any, map_id: int | None = None) -> dict | None:
    """Find one preset by id or case-insensitive name, optionally scoped to a map."""
    if ref in (None, ""):
        return None
    text = str(ref).strip()
    matches = [p for p in presets
               if (map_id is None or p["map_id"] == map_id)
               and (p["id"] == text or p["name"].casefold() == text.casefold())]
    return matches[0] if len(matches) == 1 else None
