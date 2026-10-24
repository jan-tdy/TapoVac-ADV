"""Select entities for Tapo RV30 — water level and clean passes."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cleanhistory import RETENTION_DAYS
from .const import AUTO_EMPTY_MODES, DOMAIN, WATER_INT_TO_NAME, WATER_NAME_TO_INT
from .coordinator import TapoCoordinator
from .entity import TapoEntity

_LOGGER = logging.getLogger(__name__)

PASSES_OPTIONS = ["1", "2", "3"]
WATER_OPTIONS  = ["off", "low", "medium", "high"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = [
        TapoCleanPassesSelect(coordinator, entry),
        TapoWaterLevelSelect(coordinator, entry),
    ]
    if "dust_collection_mode" in (coordinator.settings.get("dust") or {}):
        entities.append(TapoAutoEmptyModeSelect(coordinator, entry))
    entities.append(TapoHistoryRetentionSelect(coordinator, entry))
    entities.append(TapoMapRotationSelect(coordinator, entry))
    async_add_entities(entities)


class _TapoSelectBase(CoordinatorEntity[TapoCoordinator], SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self):
        return self.coordinator.device_info


class TapoCleanPassesSelect(_TapoSelectBase):
    _attr_name    = "Clean Passes"
    _attr_icon    = "mdi:repeat"
    _attr_options = PASSES_OPTIONS

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_clean_passes"

    @property
    def current_option(self) -> str | None:
        d = self.coordinator.data
        if d is None:
            return None
        return str(d.get("clean_number", 1))

    async def async_select_option(self, option: str) -> None:
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_passes, int(option)
        )
        await self.coordinator.async_request_refresh()


class TapoWaterLevelSelect(_TapoSelectBase):
    _attr_name    = "Water Level"
    _attr_icon    = "mdi:water"
    _attr_options = WATER_OPTIONS

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_water_level"

    @property
    def current_option(self) -> str | None:
        d = self.coordinator.data
        if d is None:
            return None
        return WATER_INT_TO_NAME.get(d.get("cistern", 0), "off")

    async def async_select_option(self, option: str) -> None:
        value = WATER_NAME_TO_INT.get(option)
        if value is None:
            _LOGGER.error("Unknown water level: %s", option)
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_water, value
        )
        await self.coordinator.async_request_refresh()


class TapoAutoEmptyModeSelect(TapoEntity, SelectEntity):
    """How often the self-empty dock empties the bin (Smart / Light / Balanced / Max)."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:delete-sweep"
    _attr_options = list(AUTO_EMPTY_MODES.values())

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "auto_empty_mode", "Auto Empty Mode")

    @property
    def current_option(self) -> str | None:
        return AUTO_EMPTY_MODES.get((self.settings.get("dust") or {}).get("dust_collection_mode"))

    async def async_select_option(self, option: str) -> None:
        mode = next(k for k, v in AUTO_EMPTY_MODES.items() if v == option)
        await self._write(lambda: self.coordinator.client.set_auto_empty_mode(mode))


class TapoHistoryRetentionSelect(TapoEntity, SelectEntity):
    """How long the maps of finished cleans are kept in Home Assistant (Off clears them)."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:map-clock-outline"
    _attr_options = list(RETENTION_DAYS)

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "clean_map_history", "Clean Map History")

    @property
    def current_option(self) -> str:
        return self.coordinator.history_retention

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_history(retention=option)


class TapoMapRotationSelect(TapoEntity, SelectEntity):
    """How the map is rotated wherever it is shown: one integration setting, not a
    per-browser preference, so the sidebar page, cards and automations all agree."""
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:crop-rotate"
    _attr_options = ["0", "90", "180", "270"]

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "map_rotation", "Map Rotation")

    @property
    def current_option(self) -> str:
        return str(self.coordinator.map_rotation)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_map_rotation(int(option))
