"""Tests for schedule-rule decoding in coordinator.py."""
from __future__ import annotations

import pytest

from custom_components.tapo_rv30.coordinator import _decode_schedule, _decode_weekdays


@pytest.mark.parametrize(
    "mask, expected",
    [
        # Confirmed against a real device (see coordinator.py comment): a
        # Mon/Wed/Fri schedule came back with week_day=42.
        (42, ["Mon", "Wed", "Fri"]),
        (0, []),
        (127, ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]),
        (1, ["Sun"]),
        (64, ["Sat"]),
        (65, ["Sun", "Sat"]),  # bit 0 and bit 6 only
    ],
)
def test_decode_weekdays(mask: int, expected: list[str]) -> None:
    assert _decode_weekdays(mask) == expected


def test_decode_schedule_room_list() -> None:
    rule = {
        "id": 7,
        "enable": True,
        "s_min": 9 * 60 + 30,  # 09:30
        "week_day": 42,        # Mon/Wed/Fri
        "mode": "repeat",
        "clean_attr": {
            "room_list": [1, 2],
            "clean_order": True,
            "suction": 3,
            "cistern": 2,
            "clean_number": 1,
            "clean_mode": 3,
            "map_id": 100,
        },
    }
    room_names = {1: "Living Room", 2: "Kitchen"}

    decoded = _decode_schedule(rule, room_names)

    assert decoded["id"] == 7
    assert decoded["enabled"] is True
    assert decoded["time"] == "09:30"
    assert decoded["days"] == ["Mon", "Wed", "Fri"]
    assert decoded["repeat"] is True
    assert decoded["rooms"] == ["Living Room", "Kitchen"]
    assert decoded["room_ids"] == [1, 2]
    assert decoded["clean_mode"] == 3
    assert decoded["custom_rule_id"] is None
    assert decoded["is_preset"] is False
    assert decoded["map_id"] == 100
    assert decoded["raw"] is rule


def test_decode_schedule_preset() -> None:
    """clean_mode 5 + custom_rule_id (no room_list) marks a "preset"
    schedule, and an unknown room id falls back to a generated label."""
    rule = {
        "id": 3,
        "enable": False,
        "s_min": 0,
        "week_day": 0,
        "mode": "once",
        "clean_attr": {
            "custom_rule_id": 55,
            "clean_mode": 5,
        },
    }

    decoded = _decode_schedule(rule, room_names={})

    assert decoded["time"] == "00:00"
    assert decoded["days"] == []
    assert decoded["repeat"] is False
    assert decoded["rooms"] == []
    assert decoded["custom_rule_id"] == 55
    assert decoded["is_preset"] is True


def test_decode_schedule_unknown_room_falls_back_to_generated_label() -> None:
    rule = {"id": 1, "clean_attr": {"room_list": [9]}}
    decoded = _decode_schedule(rule, room_names={})
    assert decoded["rooms"] == ["Room 9"]
