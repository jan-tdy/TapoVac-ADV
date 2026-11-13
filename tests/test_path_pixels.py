"""The map camera's `path` attribute: the cleaning path as image pixels."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.tapo_rv30 import maprender
from custom_components.tapo_rv30.coordinator import TapoCoordinator

# 100-cell-high map, 50 mm cells: grid (0, 0) is the bottom-left cell, which sits at
# image pixel (2, 398) with MAP_SCALE = 4 (y grows downwards in the picture).
MAP_DATA = {"height": 100, "real_origin_coor": [0, 0], "resolution": 50}


def test_path_pixels_use_the_map_picture_frame() -> None:
    # (500, 500) mm is grid cell (10, 10) -> pixel (10 * 4 + 2, (99 - 10) * 4 + 2).
    assert maprender.path_pixels(MAP_DATA, [(0, 0), (500, 500)]) == [[2, 398], [42, 358]]


def test_path_pixels_drop_repeats_and_handle_short_input() -> None:
    # The first three points all round to the same pixel, so only one survives.
    assert maprender.path_pixels(MAP_DATA, [(0, 0), (1, 1), (2, 1)]) == [[2, 398]]
    assert maprender.path_pixels(MAP_DATA, [(0, 0)]) == []
    assert maprender.path_pixels(MAP_DATA, []) == []


def test_coordinator_fills_path_px_even_without_a_base_image() -> None:
    coordinator = TapoCoordinator(HomeAssistant(), client=object())
    coordinator.data = {}   # no poll yet: status_code reads from here
    coordinator.path_points = [(0, 0), (500, 500)]
    assert coordinator._map_base is None
    coordinator._apply_position(MAP_DATA, docked=False)
    assert coordinator.path_px == [[2, 398], [42, 358]]
