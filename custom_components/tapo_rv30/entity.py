"""Shared base for every Tapo RV30 entity — one Home Assistant device per
config entry, described from data the coordinator fetches once at startup
(coordinator.device_name / device_model) instead of a literal model string
duplicated into every entity class (see issue #36)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoCoordinator


class TapoEntity(CoordinatorEntity[TapoCoordinator]):
    """Mixin providing device_info for every Tapo RV30 entity.

    Combine with the platform's own entity base, e.g.
    `class Foo(TapoEntity, SensorEntity)`. Platforms whose base class needs
    its own explicit `__init__` call (e.g. Camera) can call
    `TapoEntity.__init__(self, coordinator, entry)` directly instead of
    relying on cooperative `super()` — see camera.py.
    """

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self):
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self.coordinator.device_name,
            "manufacturer": "TP-Link",
            "model":        self.coordinator.device_model,
        }
