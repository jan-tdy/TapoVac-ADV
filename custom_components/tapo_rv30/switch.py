"""Switch entities for Tapo RV30 — child lock."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TapoChildLockSwitch(coordinator, entry)])


class TapoChildLockSwitch(CoordinatorEntity[TapoCoordinator], SwitchEntity):
    """Confirmed via setChildLockInfo against a real device."""
    _attr_has_entity_name = True
    _attr_name             = "Child Lock"
    _attr_icon             = "mdi:lock"

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry          = entry
        self._attr_unique_id = f"{entry.entry_id}_child_lock"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name":        self.coordinator.device_name,
            "manufacturer":"TP-Link",
            "model":       "Tapo RV30 Max Plus",
        }

    @property
    def is_on(self) -> bool | None:
        d = self.coordinator.data
        if d is None:
            return None
        return bool(d.get("child_lock", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_child_lock, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_child_lock, False
        )
        await self.coordinator.async_request_refresh()
