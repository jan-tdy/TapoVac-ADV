"""Number entities for Tapo RV30 — status poll interval and speaker volume."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, FAST_INTERVAL, MAX_FAST_INTERVAL, MIN_FAST_INTERVAL
from .coordinator import TapoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TapoRefreshIntervalNumber(coordinator, entry),
        TapoVolumeNumber(coordinator, entry),
    ])


class _TapoNumberBase(CoordinatorEntity[TapoCoordinator], NumberEntity):
    _attr_has_entity_name = True
    _attr_mode             = NumberMode.BOX

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name":        self.coordinator.device_name,
            "manufacturer":"TP-Link",
            "model":       "Tapo RV30 Max Plus",
        }


class TapoRefreshIntervalNumber(_TapoNumberBase, RestoreEntity):
    """How often (seconds) the status poll (getVacStatus/getBatteryInfo/
    getVolume/...) runs. Persisted across HA restarts via RestoreEntity —
    otherwise a restart would silently drop back to the FAST_INTERVAL
    default. Does not affect the map image refresh cadence
    (MAP_INTERVAL/MAP_INTERVAL_ACTIVE), which stays tied to the poll
    interval as a cycle count — see coordinator.py."""
    _attr_name                       = "Refresh Interval"
    _attr_icon                       = "mdi:timer-sync-outline"
    _attr_native_min_value            = MIN_FAST_INTERVAL
    _attr_native_max_value            = MAX_FAST_INTERVAL
    _attr_native_step                 = 5
    _attr_native_unit_of_measurement  = "s"

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_refresh_interval"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in (None, "unknown", "unavailable"):
            return
        try:
            seconds = float(last_state.state)
        except (TypeError, ValueError):
            return
        seconds = max(MIN_FAST_INTERVAL, min(MAX_FAST_INTERVAL, seconds))
        self.coordinator.update_interval = timedelta(seconds=seconds)

    @property
    def native_value(self) -> float:
        interval = self.coordinator.update_interval
        return interval.total_seconds() if interval else FAST_INTERVAL

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.update_interval = timedelta(seconds=value)
        await self.coordinator.async_request_refresh()


class TapoVolumeNumber(_TapoNumberBase):
    """Speaker/voice-prompt volume (0-100) — confirmed via setVolume
    against a real device."""
    _attr_name                       = "Volume"
    _attr_icon                       = "mdi:volume-high"
    _attr_native_min_value            = 0
    _attr_native_max_value            = 100
    _attr_native_step                 = 1
    _attr_native_unit_of_measurement  = "%"

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_volume"

    @property
    def native_value(self) -> float | None:
        d = self.coordinator.data
        if not d:
            return None
        return d.get("volume")

    async def async_set_native_value(self, value: float) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_volume, int(value)
        )
        await self.coordinator.async_request_refresh()
