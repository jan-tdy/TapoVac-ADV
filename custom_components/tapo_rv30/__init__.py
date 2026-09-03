"""Tapo RV30 Robot Vacuum integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import TapoCoordinator
from .tpap import TapoVacuumClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.VACUUM, Platform.SENSOR, Platform.CAMERA, Platform.SELECT,
    Platform.BINARY_SENSOR, Platform.BUTTON,
]


def _coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> TapoCoordinator | None:
    """Resolve the coordinator that owns entity_id via its config entry."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.config_entry_id is None:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)


async def _handle_clean_rooms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service: tapo_rv30.clean_rooms."""
    entity_ids: list[str] = call.data.get("entity_id", [])
    rooms_raw = call.data.get("rooms", [])
    map_name: str | None = call.data.get("map")

    # Normalise rooms to a list — HA templates can produce a string when only
    # one room is selected, and iterating a string gives individual characters.
    if isinstance(rooms_raw, str):
        rooms: list[str] = [rooms_raw]
    else:
        rooms = list(rooms_raw)

    if not rooms:
        _LOGGER.error("clean_rooms: 'rooms' field is required")
        return

    for entity_id in entity_ids:
        coord = _coordinator_for_entity(hass, entity_id)
        if coord is None:
            _LOGGER.error("clean_rooms: no tapo_rv30 device found for %s", entity_id)
            continue

        try:
            # Fetch rooms live from the device so we always use the correct map_id
            # and support the optional map_name filter.
            room_ids, map_id = await hass.async_add_executor_job(
                coord.resolve_rooms_live, rooms, map_name
            )
            await hass.async_add_executor_job(coord.client.clean_rooms, room_ids, map_id)
            # Trigger a map refresh so the in-progress path shows promptly
            await coord.async_request_refresh()
        except ValueError as exc:
            _LOGGER.error("clean_rooms: %s", exc)


async def _handle_run_schedule(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service: tapo_rv30.run_schedule."""
    entity_ids: list[str] = call.data.get("entity_id", [])
    schedule_id = call.data.get("schedule_id")
    if schedule_id is None:
        _LOGGER.error("run_schedule: 'schedule_id' field is required")
        return

    for entity_id in entity_ids:
        coord = _coordinator_for_entity(hass, entity_id)
        if coord is None:
            _LOGGER.error("run_schedule: no tapo_rv30 device found for %s", entity_id)
            continue

        try:
            await hass.async_add_executor_job(coord.client.run_schedule, schedule_id)
            # Trigger a map refresh so the in-progress path shows promptly
            await coord.async_request_refresh()
        except ValueError as exc:
            _LOGGER.error("run_schedule: %s", exc)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the tapo_rv30 services once, shared across all config entries."""
    hass.data.setdefault(DOMAIN, {})

    async def clean_rooms(call: ServiceCall) -> None:
        await _handle_clean_rooms(hass, call)

    async def run_schedule(call: ServiceCall) -> None:
        await _handle_run_schedule(hass, call)

    hass.services.async_register(DOMAIN, "clean_rooms", clean_rooms)
    hass.services.async_register(DOMAIN, "run_schedule", run_schedule)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = TapoVacuumClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=DEFAULT_PORT,
        cache_dir=hass.config.path(".storage", DOMAIN),
    )
    coordinator = TapoCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
