"""Custom-service clean settings: `fan_speed` (like vacuum.set_fan_speed), `suction` as alias."""
from __future__ import annotations

import types

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.tapo_rv30.services import _levels


def _call(**data):
    return types.SimpleNamespace(service="clean_rooms", data=data)


def test_fan_speed_field_sets_suction_level() -> None:
    assert _levels(_call(fan_speed="Quiet")) == {"suction": 1}
    assert _levels(_call(fan_speed="Ultra")) == {"suction": 5}


def test_legacy_suction_field_still_accepted() -> None:
    assert _levels(_call(suction="Turbo")) == {"suction": 3}


def test_fan_speed_wins_over_suction() -> None:
    assert _levels(_call(fan_speed="Max", suction="Quiet")) == {"suction": 4}


def test_unknown_fan_speed_is_rejected() -> None:
    with pytest.raises(ServiceValidationError, match="fan_speed"):
        _levels(_call(fan_speed="Warp"))
