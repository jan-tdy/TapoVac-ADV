"""Binary sensor entities for Tapo RV30."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TapoCoordinator
from .entity import TapoEntity


def _fmt_min(m: int | None) -> str | None:
    """Minutes-since-midnight → 'HH:MM', as used by getDoNotDisturb's
    s_min/e_min (same convention as get_schedule_rules' s_min — see
    coordinator._decode_schedule)."""
    if m is None:
        return None
    return f"{m // 60:02d}:{m % 60:02d}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TapoMopAttachedBinarySensor(coordinator, entry),
        TapoDoNotDisturbBinarySensor(coordinator, entry),
    ])


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


class TapoDoNotDisturbBinarySensor(TapoEntity, BinarySensorEntity):
    """Read-only: getDoNotDisturb confirmed against a real device
    ({'do_not_disturb': True, 's_min': 1430, 'e_min': 485}); no setter has
    been probed yet."""
    _attr_has_entity_name = True
    _attr_name             = "Do Not Disturb"
    _attr_icon             = "mdi:sleep"

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_do_not_disturb"

    @property
    def is_on(self) -> bool | None:
        d = self.coordinator.data
        if d is None:
            return None
        return bool(d.get("do_not_disturb", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data
        if not d:
            return {}
        return {
            "start": _fmt_min(d.get("dnd_start_min")),
            "end":   _fmt_min(d.get("dnd_end_min")),
        }
