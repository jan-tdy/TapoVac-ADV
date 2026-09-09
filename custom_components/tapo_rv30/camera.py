"""Camera entity serving the rendered map image for Tapo RV30."""
from __future__ import annotations

import logging
from typing import Any

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Click-to-room hit-testing data for frontend cards (e.g.
        # VacuumCard-ADV): each room's centroid/bbox/color in the exact
        # pixel space of the image this entity serves — see
        # coordinator._render_map_image()'s docstring for why that
        # (rather than raw device grid coordinates) is what's exposed here.
        return {"room_geometry": self.coordinator.room_geometry}
