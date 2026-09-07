"""Binary sensor entities for Tapo RV30."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TapoCoordinator
from .entity import TapoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TapoMopAttachedBinarySensor(coordinator, entry)])


class TapoMopAttachedBinarySensor(TapoEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name             = "Mop Attached"

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_mop_attached"

    @property
    def is_on(self) -> bool | None:
        d = self.coordinator.data
        if d is None:
            return None
        return bool(d.get("mop_attached", False))

    @property
    def icon(self) -> str:
        return "mdi:water" if self.is_on else "mdi:water-off"
