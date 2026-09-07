"""Camera entity serving the rendered map image for Tapo RV30."""
from __future__ import annotations

import logging
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TapoCoordinator
from .entity import TapoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TapoMapCamera(coordinator, entry)])


class TapoMapCamera(TapoEntity, Camera):
    _attr_has_entity_name = True
    _attr_name            = "Map"
    _attr_is_streaming    = False
    _attr_is_recording    = False

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        TapoEntity.__init__(self, coordinator, entry)
        Camera.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_map"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        return self.coordinator.map_image_bytes
