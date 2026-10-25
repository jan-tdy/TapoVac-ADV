"""Tests for the docked-vs-active map re-render cadence."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.tapo_rv30.const import DOCKED_CODES, DOCKED_MAP_INTERVAL, MAP_INTERVAL
from custom_components.tapo_rv30.coordinator import TapoCoordinator


def _coordinator() -> TapoCoordinator:
    coord = TapoCoordinator(HomeAssistant(), client=object())
    coord.poll_interval = 60
    return coord


def test_map_cycles_for_docked_status_uses_the_longer_interval() -> None:
    coord = _coordinator()
    docked_code = next(iter(DOCKED_CODES))
    assert coord._map_cycles_for(docked_code) == max(1, DOCKED_MAP_INTERVAL // coord.poll_interval)
    assert coord._map_cycles_for(docked_code) > coord._map_cycles


def test_map_cycles_for_non_docked_status_uses_the_normal_interval() -> None:
    coord = _coordinator()
    non_docked = next(c for c in range(50) if c not in DOCKED_CODES)
    assert coord._map_cycles_for(non_docked) == max(1, MAP_INTERVAL // coord.poll_interval)
    assert coord._map_cycles_for(non_docked) == coord._map_cycles


def test_request_map_refresh_forces_a_render_even_while_docked(monkeypatch) -> None:
    # async_request_map_refresh runs right after the map editor saves, which only
    # happens while docked; the tick it sets must clear the docked (larger)
    # threshold, not just the normal one.
    coord = _coordinator()
    docked_code = next(iter(DOCKED_CODES))
    coord.data = {"status_code": docked_code}

    async def fake_refresh_soon() -> None:
        return None

    monkeypatch.setattr(coord, "async_refresh_soon", fake_refresh_soon)

    import asyncio
    asyncio.run(coord.async_request_map_refresh())

    assert coord._map_tick >= coord._map_cycles_for(docked_code)
