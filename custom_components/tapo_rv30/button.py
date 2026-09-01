"""Button entities for Plus/Omni dock actions — EXPERIMENTAL, see README
"Dock support (Plus / Omni)". Only created for the specific actions the
device's firmware confirms it has (coordinator.dock_features, probed
once at startup via TapoVacuumClient.get_dock_features) — a Plus dock
(auto-empty only) typically gets just "Empty Dust Bin", an Omni dock
(all-in-one) typically gets the mop wash/dry ones too, and a plain
RV30/RV20 without any dock gets none of these entities at all."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoCoordinator

_LOGGER = logging.getLogger(__name__)

# (dock_features key, unique_id suffix, display name, icon)
_DOCK_BUTTONS = [
    ("dust_collection", "empty_dust_bin", "Empty Dust Bin", "mdi:delete-empty"),
    ("back_wash_mode",  "wash_mop",       "Wash Mop",       "mdi:water-sync"),
    ("dry_mop_mode",    "dry_mop",        "Dry Mop",        "mdi:tumble-dryer"),
    ("cut_hair_mode",   "remove_hair",    "Remove Hair",    "mdi:content-cut"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        TapoDockActionButton(
            coordinator, entry,
            feature_key=key, unique_suffix=suffix, name=name, icon=icon,
        )
        for key, suffix, name, icon in _DOCK_BUTTONS
        if key in coordinator.dock_features
    ])


class TapoDockActionButton(CoordinatorEntity[TapoCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TapoCoordinator,
        entry: ConfigEntry,
        *,
        feature_key: str,
        unique_suffix: str,
        name: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry          = entry
        self._feature_key    = feature_key
        self._attr_name      = name
        self._attr_icon      = icon
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name":        self.coordinator.device_name,
            "manufacturer":"TP-Link",
            "model":       "Tapo RV30 Max Plus",
        }

    async def async_press(self) -> None:
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.client.start_dock_action, self._feature_key
            )
        except Exception as exc:
            _LOGGER.warning("Dock action %s failed: %s", self._feature_key, exc)
            raise HomeAssistantError(
                f"Dock action {self._feature_key!r} failed: {exc}"
            ) from exc
        await self.coordinator.async_request_refresh()
