"""Tapo RV30 Robot Vacuum integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import TapoCoordinator
from .tpap import TapoVacuumClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [
    Platform.VACUUM, Platform.SENSOR, Platform.CAMERA, Platform.SELECT,
    Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SWITCH,
]

try:
    # HA 2026.10+ moved target-selector expansion out of helpers.service into
    # its own module, and changed the call signature from
    # async_extract_referenced_entity_ids(hass, call) to
    # async_extract_referenced_entity_ids(hass, TargetSelection(call.data)) —
    # the old helpers.service function was removed outright rather than kept
    # as a compatibility shim, so importing it unconditionally broke loading
    # this integration entirely (ImportError at import time).
    from homeassistant.helpers.target import TargetSelection as _TargetSelection
    from homeassistant.helpers.target import (
        async_extract_referenced_entity_ids as _async_extract_referenced_entity_ids,
    )

    def _extract_referenced_entity_ids(hass: HomeAssistant, call: ServiceCall):
        return _async_extract_referenced_entity_ids(hass, _TargetSelection(call.data))

except ImportError:
    from homeassistant.helpers.service import (
        async_extract_referenced_entity_ids as _async_extract_referenced_entity_ids_legacy,
    )

    def _extract_referenced_entity_ids(hass: HomeAssistant, call: ServiceCall):
        return _async_extract_referenced_entity_ids_legacy(hass, call)


def _target_entity_ids(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Resolve every entity_id the call was targeted at.

    services.yaml declares `target: entity`, which the UI renders with
    Devices and Areas tabs alongside Entities — but a plain
    hass.services.async_register() handler only ever sees a literal
    entity_id list in call.data, so a device/area target silently resolved
    to nothing (see #37). _extract_referenced_entity_ids (see the version
    shim above) expands all three target kinds into the actual entity_ids.
    """
    selected = _extract_referenced_entity_ids(hass, call)
    return sorted(selected.referenced | selected.indirectly_referenced)


def _coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> TapoCoordinator | None:
    """Resolve the coordinator that owns entity_id via its config entry."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.config_entry_id is None:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)


async def _handle_clean_rooms(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service: tapo_rv30.clean_rooms."""
    entity_ids = _target_entity_ids(hass, call)
    if not entity_ids:
        raise HomeAssistantError(
            "clean_rooms: no target entity resolved — select a tapo_rv30 "
            "vacuum entity, device, or area"
        )

    rooms_raw = call.data.get("rooms", [])
    map_name: str | None = call.data.get("map")

    # Normalise rooms to a list — HA templates can produce a string when only
    # one room is selected, and iterating a string gives individual characters.
    if isinstance(rooms_raw, str):
        rooms: list[str] = [rooms_raw]
    else:
        rooms = list(rooms_raw)

    if not rooms:
        raise HomeAssistantError("clean_rooms: 'rooms' field is required")

    # Every failure below is collected instead of raised immediately, so one
    # bad entity (unmatched room name, device mid-clean, ...) doesn't stop
    # the call from still reaching every other targeted vacuum — but the
    # call still surfaces a clear error at the end instead of only logging
    # it, so a mistake (or a busy/paused device) isn't silently dropped.
    errors: list[str] = []
    for entity_id in entity_ids:
        coord = _coordinator_for_entity(hass, entity_id)
        if coord is None:
            errors.append(f"{entity_id}: no tapo_rv30 device found")
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
        except (ValueError, RuntimeError) as exc:
            # ValueError: unmatched room/map name, or a busy/paused device
            # (see TapoVacuumClient._require_idle). RuntimeError: a device
            # error (e.g. "Device error -3002") from send() itself, e.g. if
            # the device's state changed between the idle check above and
            # the actual send. Either way, one entity's failure shouldn't
            # abort the loop and skip every other targeted vacuum.
            errors.append(f"{entity_id}: {exc}")

    if errors:
        for msg in errors:
            _LOGGER.error("clean_rooms: %s", msg)
        raise HomeAssistantError("clean_rooms: " + "; ".join(errors))


async def _handle_run_schedule(hass: HomeAssistant, call: ServiceCall) -> None:
    """Service: tapo_rv30.run_schedule."""
    entity_ids = _target_entity_ids(hass, call)
    if not entity_ids:
        raise HomeAssistantError(
            "run_schedule: no target entity resolved — select a tapo_rv30 "
            "vacuum entity, device, or area"
        )

    schedule_id = call.data.get("schedule_id")
    if schedule_id is None:
        raise HomeAssistantError("run_schedule: 'schedule_id' field is required")

    errors: list[str] = []
    for entity_id in entity_ids:
        coord = _coordinator_for_entity(hass, entity_id)
        if coord is None:
            errors.append(f"{entity_id}: no tapo_rv30 device found")
            continue

        try:
            await hass.async_add_executor_job(coord.client.run_schedule, schedule_id)
            # Trigger a map refresh so the in-progress path shows promptly
            await coord.async_request_refresh()
        except (ValueError, RuntimeError) as exc:
            errors.append(f"{entity_id}: {exc}")

    if errors:
        for msg in errors:
            _LOGGER.error("run_schedule: %s", msg)
        raise HomeAssistantError("run_schedule: " + "; ".join(errors))


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
