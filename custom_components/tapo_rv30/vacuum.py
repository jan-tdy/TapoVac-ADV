"""Vacuum entity for Tapo RV30."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    Segment,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    FAN_INT_TO_NAME,
    FAN_NAME_TO_INT,
    FAN_SPEED_LIST,
    VACUUM_STATES,
    WATER_INT_TO_NAME,
)
from .coordinator import TapoCoordinator, _b64name

_LOGGER = logging.getLogger(__name__)

_FEATURES = (
    VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.STATE
    | VacuumEntityFeature.MAP
    | VacuumEntityFeature.CLEAN_AREA
    | VacuumEntityFeature.CLEAN_SPOT
    | VacuumEntityFeature.SEND_COMMAND
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TapoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TapoVacuumEntity(coordinator, entry)])


class TapoVacuumEntity(CoordinatorEntity[TapoCoordinator], StateVacuumEntity):
    _attr_has_entity_name = True
    _attr_name            = None   # use device name as entity name
    _attr_supported_features = _FEATURES
    _attr_fan_speed_list     = FAN_SPEED_LIST

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry          = entry
        self._attr_unique_id = f"{entry.entry_id}_vacuum"

    @callback
    def _handle_coordinator_update(self) -> None:
        self._check_segments_drift()
        super()._handle_coordinator_update()

    def _check_segments_drift(self) -> None:
        # Raises the standard "segments changed" repair issue (the frontend
        # then points you back at the mapping dialog) if the current map's
        # rooms no longer match what was last mapped to areas. Only checks
        # the currently active map, using data the coordinator already
        # polls — checking every saved map here would mean fetching each
        # one's full map data on every coordinator refresh, which is too
        # chatty for a periodic check.
        if self.registry_entry is None:
            return
        last_seen = self.last_seen_segments
        if last_seen is None:
            return  # never mapped, nothing to compare against
        map_id = self.coordinator.map_id
        if map_id is None:
            return
        prefix = f"{map_id}:"
        last_seen_for_map = {s.id: s.name for s in last_seen if s.id.startswith(prefix)}
        if not last_seen_for_map:
            return  # last mapping was for a different map; not this check's business
        current_for_map = {
            f"{map_id}:{r['id']}": _b64name(r.get("name", ""))
            for r in self.coordinator.rooms
        }
        if last_seen_for_map != current_for_map:
            self.async_create_segments_issue()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name":        self.coordinator.device_name,
            "manufacturer":"TP-Link",
            "model":       "Tapo RV30 Max Plus",
        }

    @property
    def activity(self) -> VacuumActivity | None:
        d = self.coordinator.data
        if d is None:
            return None
        return VacuumActivity(VACUUM_STATES.get(d.get("status_code", 0), "idle"))

    @property
    def fan_speed(self) -> str | None:
        d = self.coordinator.data
        if d is None:
            return None
        return FAN_INT_TO_NAME.get(d.get("suction", 4), "Max").capitalize()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        rooms = [_b64name(r.get("name", "")) for r in self.coordinator.rooms]
        return {
            "water_level":   WATER_INT_TO_NAME.get(d.get("cistern", 0), "off"),
            "clean_passes":  d.get("clean_number", 1),
            "mop_attached":  d.get("mop_attached", False),
            "clean_area":    d.get("clean_area", 0),
            "clean_time_min":d.get("clean_time", 0),
            "clean_percent": d.get("clean_percent", 0),
            "rooms":         rooms,
            "integration":   DOMAIN,
            # Diagnostic: the raw getVacStatus code. Some transitional states
            # (e.g. LiDAR relocalizing after start/resume) aren't in
            # VACUUM_STATES yet and fall back to "idle" in `activity` — this
            # lets you see the real code so a proper mapping can be added.
            "status_code":   d.get("status_code"),
        }

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.start)
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.pause)
        await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.stop)
        await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.dock)
        await self.coordinator.async_request_refresh()

    async def async_clean_spot(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.coordinator.client.clean_spot)
        await self.coordinator.async_request_refresh()

    async def async_send_command(
        self, command: str, params: dict | list | None = None, **kwargs: Any
    ) -> None:
        # Raw passthrough to the TPAP client's send() — an escape hatch for
        # calling any device method directly (e.g. while trying to discover
        # ones this integration doesn't know about yet, like LOCATE or
        # resolving a schedule's custom_rule_id to actual rooms).
        try:
            result = await self.hass.async_add_executor_job(
                self.coordinator.client.send, command, params
            )
        except Exception as exc:
            # Re-raised as HomeAssistantError so the actual device error
            # (e.g. "Device error -X") shows up in the action's own error
            # popup/response, instead of HA's generic "Unknown error" for
            # an unhandled exception.
            _LOGGER.warning("send_command(%s, %s) failed: %s", command, params, exc)
            raise HomeAssistantError(f"send_command {command!r} failed: {exc}") from exc
        _LOGGER.info("send_command(%s, %s) -> %s", command, params, result)
        await self.coordinator.async_request_refresh()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        value = FAN_NAME_TO_INT.get(fan_speed.lower())
        if value is None:
            _LOGGER.error("Unknown fan speed: %s", fan_speed)
            return
        await self.hass.async_add_executor_job(self.coordinator.client.set_fan_speed, value)
        await self.coordinator.async_request_refresh()

    async def async_get_segments(self) -> list[Segment]:
        # Fetched live (not from the coordinator cache) since this feeds the
        # area-mapping dialog. Covers every saved map, not just the one
        # currently active — room IDs are only unique within a map, so each
        # segment's id is namespaced "<map_id>:<room_id>" and its `group` is
        # the map's own name, so multiple floors show up as separate groups
        # in the mapping dialog instead of only ever exposing whichever map
        # happened to be loaded when the dialog was opened.
        _, map_list = await self.hass.async_add_executor_job(
            self.coordinator.client.get_map_info
        )
        segments: list[Segment] = []
        for m in map_list:
            map_id = m["map_id"]
            map_name = _b64name(m.get("map_name", "")) or f"Map {map_id}"
            map_data = await self.hass.async_add_executor_job(
                self.coordinator.client.get_map_data, map_id
            )
            rooms = [a for a in map_data.get("area_list", []) if a.get("type") == "room"]
            segments.extend(
                Segment(id=f"{map_id}:{r['id']}", name=_b64name(r.get("name", "")), group=map_name)
                for r in rooms
            )
        return segments

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        # Segment ids are "<map_id>:<room_id>" (see async_get_segments). If a
        # selection spans multiple maps/floors, each map's rooms are sent as
        # a separate clean_rooms() call — the vacuum can only physically be
        # on one floor at a time, so at most the first call can actually
        # start; clean_rooms()'s own already-cleaning guard (error -3002)
        # keeps a second call from doing anything unexpected rather than
        # failing loudly. This has not been tested against a real device
        # with more than one saved map.
        by_map: dict[int, list[int]] = {}
        for sid in segment_ids:
            map_id_str, room_id_str = sid.split(":", 1)
            by_map.setdefault(int(map_id_str), []).append(int(room_id_str))

        for map_id, room_ids in by_map.items():
            await self.hass.async_add_executor_job(
                self.coordinator.client.clean_rooms, room_ids, map_id
            )
        await self.coordinator.async_request_refresh()
