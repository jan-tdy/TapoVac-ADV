"""Custom services. Registered once per Home Assistant instance and routed to
the right vacuum from the call's target, so several vacuums can coexist."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from . import backupstore, mapbackup, mapcopy
from .const import (CLEANING_CODES, DOMAIN, FAN_NAME_TO_INT, PAUSED_CODES,
                    REMOTE_CONTROL_CODE, REMOTE_DIRECTIONS, WATER_NAME_TO_INT)
from .coordinator import TapoCoordinator
from .mapdata import b64name, build_schedule_rule, decode_clean_record, dnd_active, dnd_window, encode_weekdays, fold, parse_hhmm
from .targets import INDIRECT_TARGET_KEYS, TargetError, as_list, has_indirect_target, resolve
from .tpap import RobotBusy, _opt_int
from .zone_presets import MAX_NAME_LENGTH, MAX_PRESETS, clean_presets, find_preset, normalize_zones

_LOGGER = logging.getLogger(__name__)
_ZONE_RESTORE_TASKS: dict[tuple[str, int], asyncio.Task] = {}
_ZONE_RESTORE_STORAGE_LOCKS: dict[str, asyncio.Lock] = {}
SERVICES = ("clean_rooms", "set_room_settings", "clean_zone", "run_schedule", "send_raw",
            "get_clean_records", "run_preset", "set_map", "go_to",
            "add_schedule", "set_schedule", "remove_schedule", "remove_matter_fabric", "get_matter_setup_code",
            "fetch_cloud_map_backups", "save_map_setup", "apply_map_setup", "restore_map_backup",
            "create_preset", "update_preset", "delete_preset", "remote_drive",
            "create_zone_preset", "get_zone_presets", "run_zone_preset",
            "update_zone_preset", "delete_zone_preset",
            "rename_map", "set_map_lock", "delete_map", "copy_map")

MAP_NAME_MAX = 32     # the Tapo app's map name limit


def _match_map(call: ServiceCall, names: dict[int, str], ref, exact: bool = False) -> int:
    """One map from a name or id: an id or exact name first, then (unless exact) a unique
    partial name. Writes use exact, so a short name cannot land on the wrong map."""
    if ref in (None, ""):
        raise ServiceValidationError(f"{call.service}: 'map' (name or id) is required")
    wanted = fold(str(ref).strip())
    hits = [mid for mid, n in names.items() if str(mid) == wanted or fold(n) == wanted]
    if not exact:
        hits = hits or [mid for mid, n in names.items() if wanted and wanted in fold(n)]
    if len(hits) != 1:
        raise ServiceValidationError(
            f"{call.service}: no unique map matching '{ref}'. Available: {sorted(names.values())}")
    return hits[0]


def _map_name(call: ServiceCall, value) -> str:
    """A new map name as the app would store it: NFC, runs of spaces collapsed, no control or
    invisible characters, 1 to MAP_NAME_MAX UTF-16 units (how the app counts)."""
    import unicodedata
    name = " ".join(unicodedata.normalize("NFC", str(value or "")).split())
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        raise ServiceValidationError(f"{call.service}: 'name' contains control or invisible characters")
    if not name or len(name.encode("utf-16-le")) // 2 > MAP_NAME_MAX:
        raise ServiceValidationError(f"{call.service}: 'name' must be 1 to {MAP_NAME_MAX} characters")
    return name


def _new_map_name(call: ServiceCall, names: dict[int, str], value) -> str:
    """The name for a map restored or copied as new: valid, unused, and room for it."""
    name = _map_name(call, value)
    if any(fold(n) == fold(name) for n in names.values()):
        raise ServiceValidationError(f"{call.service}: the robot already has a map called '{name}'")
    if len(names) >= mapcopy.MAX_MAPS:
        raise ServiceValidationError(f"{call.service}: the robot holds at most {mapcopy.MAX_MAPS} maps and has "
                                     f"{len(names)}; delete one first (delete_map, or the Tapo app)")
    return name


# Methods the integration itself calls while the robot is working.
SAFE_WHILE_BUSY = frozenset({
    "getVacStatus", "getCleanStatus", "getCleanInfo", "getCleanAttr", "getBatteryInfo",
    "getMopState", "getConsumablesInfo", "getAreaUnit", "getMapInfo", "getMapData",
    "getPathData", "get_device_info", "getDeviceInfo", "getCleanRecords", "getComponentList",
    "setSwitchClean", "setRobotPause", "setSwitchCharge", "playSelectAudio",
})

# Onboarding, system and factory calls from the robot's dispatcher. Never sent from HA, even
# with force: setInheritInfo belongs to first-time setup (keep the old maps or start fresh) and
# is the prime suspect for a total map wipe on this robot.
BLOCKED_METHODS = frozenset({
    "setInheritInfo", "setQuickSetupInfo", "setQuickSetupExtraInfo", "setIotCheckFlag",
    "deviceReset", "deviceReboot", "firmwareUpgrade", "setWifiInfo", "unbindDevice",
    "setDeviceInfo", "setLidarEnabled", "closeDeviceBLE",
    "set_inherit_info", "set_quick_setup_info", "set_wifi_info", "set_wireless_info",
    "set_factory_mode", "exec_atcmd", "erase_flash", "fw_download", "account_sync",
    "connect_cloud", "device_reset", "device_reboot", "unbind_device", "set_lidar_enabled",
    "set_forwarding", "debug_nbus", "test",
    # quick-setup twins and other onboarding / factory / map-deleting calls
    "set_qs_info", "set_qs_extra_info", "qs_component_nego", "getQsComponentList", "component_nego",
    "get_factory_mode", "set_button_detect_status", "clear_button_detect_status", "sync_env", "deleteMap",
})
_BLOCKED_NORM = frozenset(m.replace("_", "").lower() for m in BLOCKED_METHODS)


def _raw_methods(method: str, params: dict) -> list[str]:
    """Every method a send_raw call would run: multipleRequest carries its own list (which
    may nest), and each of those must pass the same checks as a plain call."""
    out = [method]
    if method.replace("_", "").lower() == "multiplerequest":
        for req in (params.get("requests") or []) if isinstance(params, dict) else []:
            if isinstance(req, dict):
                out += _raw_methods(str(req.get("method", "")), req.get("params") or {})
    return out


def _known(value, default):
    """The polled value, or default when the robot did not report it (None)."""
    return default if value is None else value


def _is_blocked(method: str) -> bool:
    """Blocked, or not a plain method name at all: a name with hidden characters ("\\x00", a
    zero-width space) could read as a blocked one on the robot while passing this check."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", method):
        return True
    return method.replace("_", "").lower() in _BLOCKED_NORM


def _target_entity_ids(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Expand direct and indirect HA service targets to entity IDs.

    Kept as a small compatibility boundary because HA moved target expansion
    from helpers.service to helpers.target across supported releases.
    """
    entity_ids = as_list(call.data.get("entity_id"))
    if not has_indirect_target(call.data):
        return entity_ids
    target_data = {key: call.data[key] for key in INDIRECT_TARGET_KEYS if call.data.get(key)}
    try:
        from homeassistant.helpers.target import TargetSelection, async_extract_referenced_entity_ids
        selected = async_extract_referenced_entity_ids(hass, TargetSelection(target_data))
    except ImportError:
        from homeassistant.helpers.service import async_extract_referenced_entity_ids
        selected = async_extract_referenced_entity_ids(hass, call)
    return sorted(set(entity_ids) | selected.referenced | selected.indirectly_referenced)


def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[TapoCoordinator]:
    """The coordinator(s) a call targets: named vacuum entities, or a device, area, floor or
    label that holds one. With no target, the only vacuum set up."""
    loaded: dict[str, TapoCoordinator] = hass.data.get(DOMAIN, {})
    indirect_given = has_indirect_target(call.data)
    all_targets = _target_entity_ids(hass, call)
    explicit = as_list(call.data.get("entity_id"))
    indirect = sorted(set(all_targets) - set(explicit)) if indirect_given else []
    registry = er.async_get(hass)

    def entry_of(eid: str) -> tuple[str | None, str | None] | None:
        entry = registry.async_get(eid)
        return (entry.platform, entry.config_entry_id) if entry else None

    try:
        return resolve(loaded, explicit, indirect, entry_of, DOMAIN, indirect_given)
    except TargetError as exc:
        raise ServiceValidationError(f"{call.service}: {exc}") from None


def _one(hass: HomeAssistant, call: ServiceCall) -> TapoCoordinator:
    coords = _coordinators(hass, call)
    if len(coords) > 1:
        raise ServiceValidationError(f"{call.service}: target a single vacuum")
    return coords[0]


def _rooms_list(call: ServiceCall) -> list[str]:
    """'rooms' as a list. Templates give a bare string when one room is picked,
    and iterating a string would yield single characters."""
    raw = call.data.get("rooms", [])
    rooms = [raw] if isinstance(raw, str) else list(raw)
    if not rooms:
        raise ServiceValidationError(f"{call.service}: 'rooms' (or 'room_ids') is required")
    return rooms


def _levels(call: ServiceCall) -> dict:
    out = {}
    try:
        if "suction" in call.data:
            out["suction"] = FAN_NAME_TO_INT[str(call.data["suction"]).strip().lower()]
        if "water" in call.data:
            water = call.data["water"]
            # Unquoted `water: off` in YAML arrives as False.
            out["cistern"] = WATER_NAME_TO_INT["off" if water is False else str(water).strip().lower()]
        if "passes" in call.data:
            out["clean_number"] = int(call.data["passes"])
            if not 1 <= out["clean_number"] <= 3:
                raise ValueError(f"passes {out['clean_number']}")
    except (KeyError, ValueError) as exc:
        raise ServiceValidationError(
            f"{call.service}: invalid value {exc}. suction: {list(FAN_NAME_TO_INT)}, "
            f"water: {list(WATER_NAME_TO_INT)}, passes: 1-3"
        ) from exc
    return out


async def _resolve(hass: HomeAssistant, call: ServiceCall, coord: TapoCoordinator,
                   map_id: int | None = None) -> tuple[list[int], int]:
    """Resolve rooms/map from the call, raising a user-facing error on failure. room_ids
    (from the card and panel) name rooms exactly, including unnamed and same-named ones."""
    ids = call.data.get("room_ids")
    if ids not in (None, "", []):
        try:
            ids = [int(i) for i in ([ids] if isinstance(ids, (int, str)) else ids)]
        except (TypeError, ValueError):
            raise ServiceValidationError(f"{call.service}: 'room_ids' must be a list of room numbers") from None
        rooms = []
    else:
        ids = None
        rooms = _rooms_list(call)
    try:
        return await hass.async_add_executor_job(
            coord.resolve_rooms_live, rooms, None if map_id is not None else call.data.get("map"), map_id, ids
        )
    except ValueError as exc:          # MapNotFound / RoomNotFound
        raise ServiceValidationError(f"{call.service}: {exc}") from exc
    except Exception as exc:
        raise HomeAssistantError(
            f"{call.service}: could not read maps from the vacuum: {exc}"
        ) from exc


def _require_idle(call: ServiceCall, coord: TapoCoordinator) -> None:
    """A new clean is refused by the robot (-3002) while one is running or
    paused; say so up front instead of relaying the bare device error."""
    if why := coord.start_refused():
        raise ServiceValidationError(f"{call.service}: {coord.device_name} {why}")
    busy = coord.busy
    if busy == "cleaning":
        raise ServiceValidationError(
            f"{call.service}: {coord.device_name} is already cleaning; stop or pause it first")
    if busy == "paused":
        raise ServiceValidationError(
            f"{call.service}: {coord.device_name} is paused; resume (vacuum.start) or stop it first")
    if busy:
        raise ServiceValidationError(f"{call.service}: {coord.device_name} is {busy}")


async def _send(hass: HomeAssistant, call: ServiceCall, fn, *args) -> None:
    """Run a client write, surfacing device errors to the caller."""
    try:
        await hass.async_add_executor_job(fn, *args)
    except RobotBusy as exc:
        raise ServiceValidationError(f"{call.service}: the vacuum {exc}") from exc
    except Exception as exc:
        raise HomeAssistantError(f"{call.service}: vacuum rejected the command: {exc}") from exc


async def _read(hass: HomeAssistant, call: ServiceCall, fn, *args):
    """Run a blocking robot read, surfacing failures as a readable error."""
    try:
        return await hass.async_add_executor_job(fn, *args)
    except Exception as exc:
        raise HomeAssistantError(f"{call.service}: could not read from the vacuum: {exc}") from exc


# Services that can wipe or rewrite what is on the robot (or send it anything at all): only
# admins may call them, like the write websocket commands. Automations run without a user and
# are allowed; a script runs as whoever started it, as with Home Assistant's own admin services.
ADMIN_SERVICES = frozenset({"send_raw", "restore_map_backup", "apply_map_setup", "save_map_setup",
                            "fetch_cloud_map_backups", "delete_preset", "remove_schedule",
                            "remove_matter_fabric", "create_zone_preset", "update_zone_preset",
                            "delete_zone_preset", "rename_map", "set_map_lock", "delete_map", "copy_map"})


def _admin_only(hass: HomeAssistant, handler):
    async def wrapped(call: ServiceCall):
        if call.context.user_id:
            user = await hass.auth.async_get_user(call.context.user_id)
            if user is None or not user.is_admin:
                raise Unauthorized(context=call.context)
        return await handler(call)
    return wrapped


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services once (safe to call per config entry)."""
    if hass.services.has_service(DOMAIN, SERVICES[0]):
        return

    async def handle_clean_rooms(call: ServiceCall) -> None:
        want = call.data.get("map_id")
        if want not in (None, ""):
            try:
                want = int(want)
            except (TypeError, ValueError):
                raise ServiceValidationError(f"{call.service}: 'map_id' must be a map number") from None
        else:
            want = None
        levels = _levels(call) or None
        # Every robot is checked before any is started, so a call for two robots does not
        # start one and then fail on the other.
        plans = []
        for coord in _coordinators(hass, call):
            _require_idle(call, coord)
            # map_id (sent by the card and panel with room_ids): the rooms were picked on that
            # map. The robot cleans its current map, so refuse if it has moved to another.
            if want is not None and coord.map_id != want:
                raise ServiceValidationError(
                    f"{call.service}: {coord.device_name} is now on another map (the rooms were picked on "
                    f"map {want}); refresh and pick the rooms again")
            plans.append((coord, *await _resolve(hass, call, coord, map_id=want)))
        for coord, room_ids, map_id in plans:
            await _send(hass, call, coord.client.clean_rooms, room_ids, map_id, True, levels)
            await coord.async_refresh_soon()

    async def handle_set_room_settings(call: ServiceCall) -> None:
        for coord in _coordinators(hass, call):
            room_ids, map_id = await _resolve(hass, call, coord)
            lv = _levels(call)
            try:
                await hass.async_add_executor_job(coord.client.set_room_settings, map_id, dict.fromkeys(room_ids, lv))
            except Exception as exc:
                if "-1001" in str(exc):
                    raise ServiceValidationError(
                        f"{call.service}: {coord.device_name}'s firmware does not store per-room settings "
                        "(it rejects setCleanAttr type custom). Give suction / water / passes to "
                        "tapo_rv30.clean_rooms for a single run, or make a preset with per-room levels "
                        "(tapo_rv30.create_preset) and run it with tapo_rv30.run_preset.") from exc
                raise HomeAssistantError(f"{call.service}: vacuum rejected the command: {exc}") from exc
            await coord.async_request_refresh()

    async def _start_zone_clean(call: ServiceCall, coord: TapoCoordinator, map_id: int,
                                zones: list[list[int]], levels: dict) -> None:
        """Run rectangles, then restore the robot-owned map areas they temporarily replace."""
        try:
            before = await hass.async_add_executor_job(coord.client.get_map_data, map_id)
            saved_areas = [a for a in before.get("area_list") or [] if a.get("type") == "area"]
        except Exception as exc:
            _LOGGER.debug("Could not read the map's saved zones before an ad-hoc clean: %s", exc)
            saved_areas = None
        entry_id = coord.entry.entry_id
        # Keep a separate earliest snapshot for every map, in case the robot switches maps
        # while a previous restoration is still waiting or retrying.
        existing = await _zone_restore_get(hass, entry_id, map_id)
        if existing is None and saved_areas is not None:
            await _zone_restore_put(hass, entry_id, map_id, saved_areas)
        try:
            await _send(hass, call, coord.client.clean_zones, map_id, zones,
                        levels["suction"], levels["cistern"], levels["clean_number"])
        except Exception:
            if existing is None and saved_areas is not None:
                await _zone_restore_drop(hass, entry_id, map_id)
            raise
        saved = existing if existing is not None else saved_areas
        if saved is not None:
            _schedule_zone_restore(hass, entry_id, map_id, saved)
        # Refresh the full map on the first delayed poll so the temporary clean
        # rectangle does not linger in the rendered map after the robot accepts it.
        coord._map_tick = max(coord._map_tick, coord._map_cycles_for(coord.status_code) - 1)
        await coord.async_refresh_soon()

    async def handle_clean_zone(call: ServiceCall) -> None:
        coord = _one(hass, call)        # zones are in one map's coordinate frame
        _require_idle(call, coord)
        g = coord.data or {}
        levels = {"suction": _known(g.get("suction"), 3), "cistern": _known(g.get("cistern"), 0),
                  "clean_number": 1, **_levels(call)}
        try:
            zones = normalize_zones(call.data.get("zones"))
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from None
        try:
            map_id, _ = await hass.async_add_executor_job(coord.client.get_map_info)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: could not read maps from the vacuum: {exc}") from exc
        await _start_zone_clean(call, coord, int(map_id), zones, levels)

    async def _zone_preset_data(call: ServiceCall, coord: TapoCoordinator) -> tuple[list[dict], int, str]:
        store = coord._zone_preset_store
        if store is None:
            raise HomeAssistantError(f"{call.service}: zone presets need a configured vacuum")
        raw = await store.async_load()
        try:
            map_id, map_list = await hass.async_add_executor_job(coord.client.get_map_info)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: could not read the active map: {exc}") from exc
        stored = raw.get("presets") if isinstance(raw, dict) else []
        active = next((m for m in map_list if m.get("map_id") == map_id), {})
        map_name = b64name(active.get("map_name", "")) or (coord.map_name if coord.map_id == map_id else "")
        return clean_presets(stored), int(map_id), map_name

    async def _save_zone_preset_data(coord: TapoCoordinator, presets: list[dict]) -> None:
        await coord._zone_preset_store.async_save({"presets": presets})

    async def handle_get_zone_presets(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        presets, map_id, map_name = await _zone_preset_data(call, coord)
        return {"presets": presets, "map_id": map_id, "map_name": map_name}

    async def handle_create_zone_preset(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        name = str(call.data.get("name", "")).strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ServiceValidationError(f"{call.service}: 'name' must contain 1 to {MAX_NAME_LENGTH} characters")
        try:
            zones = normalize_zones(call.data.get("zones"))
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from None
        async with coord.zone_preset_lock:
            presets, map_id, map_name = await _zone_preset_data(call, coord)
            requested_map = call.data.get("map_id")
            if requested_map not in (None, ""):
                try:
                    requested_map = int(requested_map)
                except (TypeError, ValueError):
                    raise ServiceValidationError(f"{call.service}: 'map_id' must be a map number") from None
                if requested_map != map_id:
                    raise ServiceValidationError(f"{call.service}: the vacuum switched maps while the zone was being drawn")
            if len(presets) >= MAX_PRESETS:
                raise ServiceValidationError(f"{call.service}: at most {MAX_PRESETS} zone presets can be saved per vacuum")
            if any(p["map_id"] == map_id and p["name"].casefold() == name.casefold() for p in presets):
                raise ServiceValidationError(f"{call.service}: a zone preset called '{name}' already exists on this map")
            preset = {"id": uuid.uuid4().hex, "name": name, "map_id": map_id,
                      "map_name": map_name, "zones": zones}
            presets.append(preset)
            await _save_zone_preset_data(coord, presets)
        return {"preset": preset}

    async def handle_run_zone_preset(call: ServiceCall) -> None:
        coord = _one(hass, call)
        _require_idle(call, coord)
        presets, map_id, _map_name = await _zone_preset_data(call, coord)
        preset = find_preset(presets, call.data.get("preset"))
        if preset is None:
            raise ServiceValidationError(f"{call.service}: no unique zone preset matching {call.data.get('preset')!r}")
        if preset["map_id"] != map_id:
            raise ServiceValidationError(
                f"{call.service}: '{preset['name']}' belongs to map {preset['map_id']}; "
                "switch the vacuum to that saved map before running it")
        levels = {"suction": _known((coord.data or {}).get("suction"), 3),
                  "cistern": _known((coord.data or {}).get("cistern"), 0),
                  "clean_number": 1, **_levels(call)}
        await _start_zone_clean(call, coord, map_id, preset["zones"], levels)

    async def handle_update_zone_preset(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        async with coord.zone_preset_lock:
            presets, _map_id, _map_name = await _zone_preset_data(call, coord)
            preset = find_preset(presets, call.data.get("preset"))
            if preset is None:
                raise ServiceValidationError(f"{call.service}: no unique zone preset matching {call.data.get('preset')!r}")
            name = str(call.data.get("name", preset["name"])).strip()
            if not name or len(name) > MAX_NAME_LENGTH:
                raise ServiceValidationError(f"{call.service}: 'name' must contain 1 to {MAX_NAME_LENGTH} characters")
            if any(p["id"] != preset["id"] and p["map_id"] == preset["map_id"]
                   and p["name"].casefold() == name.casefold() for p in presets):
                raise ServiceValidationError(f"{call.service}: a zone preset called '{name}' already exists on this map")
            if "zones" in call.data:
                try:
                    preset["zones"] = normalize_zones(call.data["zones"])
                except ValueError as exc:
                    raise ServiceValidationError(f"{call.service}: {exc}") from None
            preset["name"] = name
            await _save_zone_preset_data(coord, presets)
        return {"preset": preset}

    async def handle_delete_zone_preset(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        if not call.data.get("confirm"):
            raise ServiceValidationError(f"{call.service}: this deletes the saved zone; set confirm: true")
        async with coord.zone_preset_lock:
            presets, _map_id, _map_name = await _zone_preset_data(call, coord)
            preset = find_preset(presets, call.data.get("preset"))
            if preset is None:
                raise ServiceValidationError(f"{call.service}: no unique zone preset matching {call.data.get('preset')!r}")
            presets = [p for p in presets if p["id"] != preset["id"]]
            await _save_zone_preset_data(coord, presets)
        return {"deleted": preset["name"], "presets": presets}

    async def handle_go_to(call: ServiceCall) -> None:
        """Drive to a point given in map mm (same frame as position_mm / clean_zone)."""
        coord = _one(hass, call)
        if coord.map_lock.locked():
            raise ServiceValidationError(f"{call.service}: {coord.device_name} is having its map written; try again shortly")
        if not coord.has("goto_point"):
            raise ServiceValidationError(f"{call.service}: {coord.device_name} does not support go-to-point")
        _require_idle(call, coord)
        try:
            x, y = int(call.data["x"]), int(call.data["y"])
        except (KeyError, TypeError, ValueError):
            raise ServiceValidationError(f"{call.service}: 'x' and 'y' (integers, mm) are required") from None
        await _send(hass, call, coord.client.goto_point, x, y)
        await coord.async_refresh_soon()

    async def handle_remote_drive(call: ServiceCall) -> ServiceResponse:
        """The app's remote control: enter, hold a direction, stop, exit. One call per step;
        the sidebar page repeats the held direction like the app does."""
        coord = _one(hass, call)
        if not coord.has("direction_control"):
            raise ServiceValidationError(f"{call.service}: {coord.device_name} has no remote control")
        command = str(call.data.get("command", "")).strip().lower()
        if command not in ("enter", "exit", *REMOTE_DIRECTIONS):
            raise ServiceValidationError(f"{call.service}: 'command' must be one of enter, forward, backward, left, "
                                         f"right, stop, exit (got {command!r})")
        if command == "exit":
            await _send(hass, call, coord.client.remote_control, False)
            await coord.async_refresh_soon()
            return {}
        if coord.status_code != REMOTE_CONTROL_CODE and coord.busy:
            raise ServiceValidationError(f"{call.service}: {coord.device_name} is {coord.busy}; stop it before taking control")
        if command == "enter":
            try:
                away_ms = await hass.async_add_executor_job(coord.client.remote_control, True)
            except Exception as exc:
                raise HomeAssistantError(f"{call.service}: vacuum rejected the command: {exc}") from exc
            await coord.async_refresh_soon()
            return {"leaving_dock_ms": away_ms or 4000}
        await _send(hass, call, coord.client.remote_drive, REMOTE_DIRECTIONS[command])
        return {"direction": REMOTE_DIRECTIONS[command]}

    async def _schedule_clean_attr(call: ServiceCall, coord: TapoCoordinator, base: dict | None) -> dict:
        """clean_attr for a schedule from rooms / preset / whole house plus levels.
        Starts from `base` (an existing rule's clean_attr) when editing."""
        attr = dict(base or {})
        g = coord.data or {}
        # room_ids (the sidebar page sends them) name rooms exactly, unnamed or same-named ones too.
        if "rooms" in call.data or "room_ids" in call.data or "preset" in call.data:
            attr.pop("room_list", None); attr.pop("custom_rule_id", None)
            if call.data.get("preset") not in (None, ""):
                preset = coord.find_preset(call.data["preset"])
                if preset is None:
                    raise ServiceValidationError(f"{call.service}: no preset matching {call.data['preset']!r}")
                attr.update({"clean_mode": 5, "custom_rule_id": preset["id"], "map_id": preset.get("map_id") or coord.map_id})
            elif call.data.get("rooms") or call.data.get("room_ids"):
                room_ids, map_id = await _resolve(hass, call, coord)
                attr.update({"clean_mode": 3, "room_list": room_ids, "map_id": map_id})
            else:
                attr.update({"clean_mode": 0, "map_id": coord.map_id})
        elif "clean_mode" not in attr:
            attr.update({"clean_mode": 0, "map_id": coord.map_id})
        attr.setdefault("suction", _known(g.get("suction"), 2))
        attr.setdefault("cistern", _known(g.get("cistern"), 0))
        attr.setdefault("clean_number", _known(g.get("clean_number"), 1))
        attr.setdefault("clean_order", True)
        attr.update(_levels(call))
        return attr

    def _check_dnd(call: ServiceCall, coord: TapoCoordinator, minutes: int, enabled: bool) -> None:
        """The robot does not run a schedule whose start falls inside Do Not Disturb
        (verified: it stays docked, nothing is logged). The app warns; we refuse unless
        the caller says ignore_dnd, so an automation can't quietly create a dead schedule."""
        dnd = coord.settings.get("dnd")
        if not enabled or call.data.get("ignore_dnd") or not dnd_active(dnd, minutes):
            return
        w = dnd_window(dnd)
        raise ServiceValidationError(
            f"{call.service}: {minutes // 60:02d}:{minutes % 60:02d} is inside {coord.device_name}'s Do Not Disturb "
            f"window ({w['start']} to {w['end']}), so the robot would never run it. Move the time, change the "
            f"Do Not Disturb times, or pass ignore_dnd: true to save it anyway.")

    async def handle_add_schedule(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        try:
            minutes = parse_hhmm(call.data.get("time"))
            mask = encode_weekdays(call.data.get("days"))
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from exc
        if not mask:
            raise ServiceValidationError(f"{call.service}: 'days' is required (Mon..Sun, daily, weekdays or weekend); "
                                         "one-off schedules are not supported, the robot stored a different date in testing")
        _check_dnd(call, coord, minutes, call.data.get("enabled", True))
        attr = await _schedule_clean_attr(call, coord, None)
        rule = build_schedule_rule(minutes, mask, attr, enabled=call.data.get("enabled", True))
        try:
            new_id = await hass.async_add_executor_job(coord.client.add_schedule, rule)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the schedule: {exc}") from exc
        await coord.async_settings_changed()
        return {"id": new_id}

    def _find_rule(call: ServiceCall, coord: TapoCoordinator, rules: list | None = None) -> dict:
        sid = str(call.data.get("schedule_id", "")).strip()
        if not sid:
            raise ServiceValidationError(f"{call.service}: 'schedule_id' is required (e.g. S1)")
        if rules is None:
            rules = (coord.settings.get("schedules") or {}).get("rule_list") or []
        rule = next((r for r in rules if str(r.get("id")) == sid), None)
        if rule is None:
            raise ServiceValidationError(f"{call.service}: no schedule {sid!r}; known: {[r.get('id') for r in rules]}")
        return rule

    async def handle_set_schedule(call: ServiceCall) -> None:
        coord = _one(hass, call)
        # editScheduleRule replaces the whole rule, built from a read of it: two edits at
        # once (or one against a stale poll) would each put back what the other changed.
        async with coord.schedule_lock:
            await _set_schedule(call, coord)

    async def _set_schedule(call: ServiceCall, coord: TapoCoordinator) -> None:
        fresh = await _read(hass, call, coord.client.get_schedules)
        rule = dict(_find_rule(call, coord, fresh))
        try:
            minutes = parse_hhmm(call.data["time"]) if "time" in call.data else rule.get("s_min", 0)
            mask = encode_weekdays(call.data["days"]) if "days" in call.data else rule.get("week_day", 0)
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from exc
        once = rule.get("mode") == "once" and "days" not in call.data
        if not mask and not once:
            raise ServiceValidationError(f"{call.service}: 'days' must leave at least one day")
        enabled = call.data.get("enabled", rule.get("enable", True))
        if "time" in call.data or call.data.get("enabled"):
            _check_dnd(call, coord, minutes, enabled)
        attr = await _schedule_clean_attr(call, coord, rule.get("clean_attr") or {})
        once_date = None
        if once and rule.get("year"):
            import datetime as _dt
            once_date = _dt.date(int(rule["year"]), int(rule["month"]), int(rule["day"]))
        body = build_schedule_rule(minutes, 0 if once else mask, attr, enabled=enabled,
                                   once_date=once_date, rule_id=rule["id"])
        # editScheduleRule replaces the whole rule: keep what the app set that this call does
        # not change (the pre-start reminder and its lead time).
        for key in ("start_remind", "alarm_min"):
            if key in rule:
                body[key] = rule[key]
        try:
            await hass.async_add_executor_job(coord.client.edit_schedule, body)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the change: {exc}") from exc
        await coord.async_settings_changed()

    async def handle_remove_schedule(call: ServiceCall) -> None:
        coord = _one(hass, call)
        if call.data.get("all"):
            ids, remove_all = [], True
        else:
            ids, remove_all = [_find_rule(call, coord)["id"]], False
        try:
            await hass.async_add_executor_job(coord.client.remove_schedules, ids, remove_all)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the removal: {exc}") from exc
        await coord.async_settings_changed()

    async def handle_remove_matter_fabric(call: ServiceCall) -> None:
        """Unpair the robot from one Matter ecosystem (fabric_index from the Matter sensor)."""
        coord = _one(hass, call)
        if not coord.has("matter"):
            raise ServiceValidationError(f"{call.service}: {coord.device_name} has no Matter support")
        try:
            idx = int(call.data["fabric_index"])
        except (KeyError, TypeError, ValueError):
            raise ServiceValidationError(f"{call.service}: 'fabric_index' (integer, see the Matter sensor) is required") from None
        known = [f.get("fabric_index") for f in ((coord.settings.get("matter_status") or {}).get("bind_fabrics") or [])]
        if known and idx not in known:
            raise ServiceValidationError(f"{call.service}: fabric {idx} is not paired; known fabrics: {known}")
        await _send(hass, call, coord.client.remove_matter_fabric, idx)
        await coord.async_settings_changed()

    async def handle_get_matter_setup_code(call: ServiceCall) -> ServiceResponse:
        """The robot's Matter pairing code and QR payload, for admins only: never in entity
        state, where every user and the recorder would see it."""
        coord = _one(hass, call)
        if not coord.has("matter"):
            raise ServiceValidationError(f"{call.service}: {coord.device_name} has no Matter support")
        info = coord.settings.get("matter_setup")
        if not isinstance(info, dict) or not info.get("setup_code"):
            try:
                info = await hass.async_add_executor_job(coord.client.send, "getMatterSetupInfo")
                info = (info or {}).get("result") or {}
            except Exception as exc:
                raise HomeAssistantError(f"{call.service}: could not read the setup code: {exc}") from exc
        return {"setup_code": info.get("setup_code"), "setup_payload": info.get("setup_payload")}

    async def handle_run_schedule(call: ServiceCall) -> None:
        """Replays a saved schedule's settings; see services.yaml."""
        coord = _one(hass, call)
        _require_idle(call, coord)
        sid = call.data.get("schedule_id")
        if sid is None:
            raise ServiceValidationError(f"{call.service}: 'schedule_id' is required")
        try:
            await hass.async_add_executor_job(coord.client.run_schedule, str(sid))
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from exc
        except RobotBusy as exc:
            raise ServiceValidationError(f"{call.service}: the vacuum {exc}") from exc
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the command: {exc}") from exc
        await coord.async_refresh_soon()

    async def handle_send_raw(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        method = str(call.data.get("method", "")).strip()
        if not method:
            raise ServiceValidationError(f"{call.service}: 'method' is required")
        params = call.data.get("params") or {}
        if isinstance(params, str):     # typed as JSON text, as in the action form's example
            try:
                params = json.loads(params)
            except ValueError:
                pass
        if not isinstance(params, dict):
            raise ServiceValidationError(f"{call.service}: 'params' must be a mapping")
        methods = _raw_methods(method, params)
        blocked = [m for m in methods if _is_blocked(m)]
        if blocked:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", blocked[0]):
                raise ServiceValidationError(
                    f"{call.service}: {blocked[0]!r} is not a plain method name (letters, digits and _ only)")
            raise ServiceValidationError(
                f"{call.service}: '{blocked[0]}' is an onboarding, system or factory call and is blocked. "
                "Calls like this have wiped this robot's maps; use the Tapo app for them.")
        # Probing a robot mid-run is how the author lost a map set and the robot's
        # clean history (see README, "Protocol notes"). Known-safe status reads are
        # allowed; anything else waits for the robot to be idle unless forced.
        unsafe = [m for m in methods if m not in SAFE_WHILE_BUSY and m != "multipleRequest"]
        if coord.map_busy and unsafe and not call.data.get("force"):
            raise ServiceValidationError(
                f"{call.service}: {coord.device_name} is {coord.map_busy}; '{unsafe[0]}' is not on the "
                f"known-safe list, so it is refused until the robot is idle (pass force: true to override)")
        try:
            resp = await hass.async_add_executor_job(coord.client.send, method, params)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: {method} failed: {exc}") from exc
        return {"result": resp.get("result"), "error_code": resp.get("error_code", 0)}

    async def handle_get_clean_records(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        try:
            raw = await hass.async_add_executor_job(coord.client.get_clean_records)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: {exc}") from exc
        records = sorted((decode_clean_record(r) for r in raw.get("record_list") or []),
                         key=lambda r: r["started"] or 0, reverse=True)
        limit = call.data.get("limit")
        if limit:
            records = records[:int(limit)]
        return {
            "total_runs": raw.get("total_number"),
            "total_area": raw.get("total_area"),
            "total_minutes": raw.get("total_time"),
            "records": records,
        }

    async def handle_run_preset(call: ServiceCall) -> None:
        coord = _one(hass, call)
        _require_idle(call, coord)
        ref = call.data.get("preset")
        if ref in (None, ""):
            raise ServiceValidationError(f"{call.service}: 'preset' (name or id) is required")
        preset = coord.find_preset(ref)
        if preset is None:
            names = [p["name"] for p in coord.presets]
            raise ServiceValidationError(
                f"{call.service}: no unique preset matching '{ref}'. Available: {names}")
        await _send(hass, call, coord.client.run_preset, preset["id"], preset["map_id"],
                    preset.get("clean_order", True))
        await coord.async_refresh_soon()

    # ---- presets (the robot's own "customisation rules", as the Tapo app edits them) ----
    def _preset_rooms(coord: TapoCoordinator, map_id: int, room_ids: list[int], lv: dict,
                      keep: dict[int, dict] | None = None) -> list[dict]:
        """Preset room items in cleaning order. Levels: the call's, else the room's existing
        ones in this preset, else the robot's current settings. Carpet handling is copied from
        the map's room, as the app does. Blocking."""
        g = coord.data or {}
        data = coord.client.get_map_data(map_id)
        carpet = {a["id"]: a.get("carpet_strategy") for a in data.get("area_list", []) if a.get("type") == "room"}
        out = []
        for rid in room_ids:
            old = (keep or {}).get(rid, {})
            out.append({"id": rid,
                        "suction": lv.get("suction", old.get("suction", _known(g.get("suction"), 2))),
                        "cistern": lv.get("cistern", old.get("cistern", _known(g.get("cistern"), 1))),
                        "clean_number": lv.get("clean_number", old.get("clean_number", 1)),
                        "carpet_strategy": old.get("carpet_strategy", carpet.get(rid))})
        return out

    def _preset_for(call: ServiceCall, coord: TapoCoordinator) -> dict:
        ref = call.data.get("preset")
        if ref in (None, ""):
            raise ServiceValidationError(f"{call.service}: 'preset' (name or id) is required")
        preset = coord.find_preset(ref)
        if preset is None:
            raise ServiceValidationError(
                f"{call.service}: no unique preset matching '{ref}'. Available: {[p['name'] for p in coord.presets]}")
        return preset

    async def _write_preset(call: ServiceCall, coord: TapoCoordinator, body: dict) -> None:
        try:
            code = await hass.async_add_executor_job(coord.client.add_preset, body)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the preset: {exc}") from exc
        if code:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the preset (error {code})")

    async def handle_create_preset(call: ServiceCall) -> ServiceResponse:
        from .mapdata import fold, preset_body
        coord = _one(hass, call)
        name = str(call.data.get("name", "")).strip()
        if not name:
            raise ServiceValidationError(f"{call.service}: 'name' is required")
        room_ids, map_id = await _resolve(hass, call, coord)
        if any(fold(p["name"]) == fold(name) and p["map_id"] == map_id for p in coord.presets):
            raise ServiceValidationError(f"{call.service}: a preset called '{name}' already exists on that map")
        rooms = await _read(hass, call, _preset_rooms, coord, map_id, room_ids, _levels(call))
        await _write_preset(call, coord, preset_body(name, map_id, rooms, call.data.get("clean_order", True)))
        await coord.async_settings_changed()
        made = next((p for p in coord.presets if fold(p["name"]) == fold(name) and p["map_id"] == map_id), None)
        return {"preset_id": made and made["id"], "name": name, "map_id": map_id, "rooms": made and made["rooms"]}

    async def handle_update_preset(call: ServiceCall) -> ServiceResponse:
        from .mapdata import b64name, preset_body
        coord = _one(hass, call)
        preset = _preset_for(call, coord)
        map_id, rule_id = preset["map_id"], preset["id"]
        try:
            detail = await hass.async_add_executor_job(coord.client.get_preset_detail, map_id, rule_id)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: could not read the preset: {exc}") from exc
        keep = {a["id"]: a for a in detail.get("area_list") or [] if a.get("type") == "room"}
        if "rooms" in call.data or "room_ids" in call.data:
            # Rooms are matched on the preset's own map (by id: it may be unnamed or share a
            # name), which need not be the active one.
            room_ids, rmap = await _resolve(hass, call, coord, map_id=map_id)
            if rmap != map_id:
                raise ServiceValidationError(f"{call.service}: the rooms must be on the preset's own map")
        else:
            room_ids = list(keep)
        rooms = await _read(hass, call, _preset_rooms, coord, map_id, room_ids, _levels(call), keep)
        name = str(call.data.get("name") or b64name(detail.get("rule_name", ""))).strip()
        order = call.data.get("clean_order", detail.get("clean_order", True))
        await _write_preset(call, coord, preset_body(name, map_id, rooms, order, rule_id=rule_id))
        await coord.async_settings_changed()
        now = coord.find_preset(rule_id)
        return {"preset_id": rule_id, "name": now and now["name"], "rooms": now and now["room_settings"]}

    async def handle_delete_preset(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        if not call.data.get("confirm"):
            raise ServiceValidationError(f"{call.service}: this deletes the preset; set confirm: true")
        preset = _preset_for(call, coord)
        try:
            code = await hass.async_add_executor_job(coord.client.delete_preset, preset["map_id"], preset["id"])
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the delete: {exc}") from exc
        if code:
            raise HomeAssistantError(f"{call.service}: vacuum rejected the delete (error {code})")
        await coord.async_settings_changed()
        return {"deleted": preset["name"], "preset_id": preset["id"],
                "remaining": [p["name"] for p in coord.presets]}

    async def handle_set_map(call: ServiceCall) -> None:
        coord = _one(hass, call)
        _require_idle(call, coord)
        ref = call.data.get("map")
        if ref in (None, ""):
            raise ServiceValidationError(f"{call.service}: 'map' (name or id) is required")
        try:
            names = await hass.async_add_executor_job(coord.map_names)
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: could not read maps from the vacuum: {exc}") from exc
        from .mapdata import fold
        wanted = fold(str(ref).strip())
        hits = [mid for mid, n in names.items() if str(mid) == wanted or fold(n) == wanted]
        hits = hits or [mid for mid, n in names.items() if wanted and wanted in fold(n)]
        if len(hits) != 1:
            raise ServiceValidationError(
                f"{call.service}: no unique map matching '{ref}'. Available: {sorted(names.values())}")
        await _send(hass, call, coord.client.set_current_map, hits[0])
        await coord.async_request_map_refresh()

    async def handle_rename_map(call: ServiceCall) -> ServiceResponse:
        """Rename a saved map. Everything in this integration (schedules, presets, room
        freshness, the planner, area mappings, setups, history) follows maps by id, so only
        references by the old name (automations passing map: <name>) need updating."""
        coord = _one(hass, call)
        _require_idle(call, coord)
        new = _map_name(call, call.data.get("name"))
        if coord.map_lock.locked():
            raise ServiceValidationError(f"{call.service}: {coord.device_name} is having its map written; "
                                         "try again shortly")
        async with coord.map_lock:
            # Names and saved state from one fresh read: the cached map list can lag a new map.
            _, map_list = await _read(hass, call, coord.client.get_map_info)
            names = {m["map_id"]: b64name(m.get("map_name", "")) for m in map_list}
            map_id = _match_map(call, names, call.data.get("map"), exact=True)
            old = names.get(map_id) or ""
            entry = next(m for m in map_list if m["map_id"] == map_id)
            if entry.get("is_saved") is not True:
                raise ServiceValidationError(f"{call.service}: that map is not saved yet; save it in the "
                                             "Tapo app first")
            if new == old:
                raise ServiceValidationError(f"{call.service}: the map is already called '{old}'")
            # Another map's name may not equal, contain or sit inside the new one: references by
            # name match exactly first, then by part, so either would retarget them silently.
            clash = [n for mid, n in names.items() if mid != map_id and n
                     and (fold(n) in fold(new) or fold(new) in fold(n))]
            if clash:
                raise ServiceValidationError(f"{call.service}: '{new}' is too close to another map's name "
                                             f"'{clash[0]}'; references by name could pick the wrong map")
            await _send(hass, call, coord.client.rename_map, map_id, new)
            try:
                after = await _read(hass, call, coord.map_names)
            finally:
                await coord.async_request_map_refresh()
        if after.get(map_id) != new:
            raise HomeAssistantError(f"{call.service}: the robot accepted the rename but still reports "
                                     f"'{after.get(map_id)}'")
        return {"map_id": map_id, "old_name": old, "name": new}

    async def handle_set_map_lock(call: ServiceCall) -> ServiceResponse:
        """Lock or unlock a map, as in the app: locked, later cleans no longer update it (room
        names, no-go zones and furniture can still be edited). Only offered when the robot's
        map list reports a lock state at all."""
        coord = _one(hass, call)
        locked = call.data.get("locked")
        if not isinstance(locked, bool):
            raise ServiceValidationError(f"{call.service}: 'locked' must be true or false")
        names = await _read(hass, call, coord.map_names)
        map_id = _match_map(call, names, call.data.get("map", coord.map_id), exact=True)
        if coord.map_lock.locked():
            raise ServiceValidationError(f"{call.service}: {coord.device_name} is having its map written; "
                                         "try again shortly")
        async with coord.map_lock:
            _, map_list = await _read(hass, call, coord.client.get_map_info)
            entry = next((m for m in map_list if m.get("map_id") == map_id), None)
            if entry is None or "map_locked" not in entry:
                raise ServiceValidationError(f"{call.service}: {coord.device_name} does not report map "
                                             "locking for this map")
            await _send(hass, call, coord.client.set_map_locked, map_id, locked)
            try:
                _, after_list = await _read(hass, call, coord.client.get_map_info)
            finally:
                await coord.async_request_map_refresh()
        after_entry = next((m for m in after_list if m.get("map_id") == map_id), {})
        if bool(after_entry.get("map_locked")) != locked:
            raise HomeAssistantError(f"{call.service}: the robot did not confirm the lock change")
        return {"map_id": map_id, "name": names.get(map_id), "locked": locked}

    async def handle_delete_map(call: ServiceCall) -> ServiceResponse:
        """Delete a map from the robot, as the Tapo app does. Never the current map (switch
        first) and never the last saved one; named in full or by id; docked and idle."""
        coord = _one(hass, call)
        if not call.data.get("confirm"):
            raise ServiceValidationError(f"{call.service}: this deletes a map from the robot; set confirm: true")
        names = await _read(hass, call, coord.map_names)
        map_id = _match_map(call, names, call.data.get("map"), exact=True)
        if coord.map_busy:
            raise ServiceValidationError(f"{call.service}: {coord.device_name} must be docked and idle")
        if coord.map_lock.locked():
            raise ServiceValidationError(f"{call.service}: a map write is running; try again shortly")
        async with coord.map_lock:
            current, map_list = await _read(hass, call, coord.client.get_map_info)
            ids = [m.get("map_id") for m in map_list]
            if map_id not in ids:
                raise ServiceValidationError(f"{call.service}: '{names.get(map_id)}' is not on the robot any more")
            if map_id == current:
                raise ServiceValidationError(f"{call.service}: '{names.get(map_id)}' is the current map; switch "
                                             "to another map first")
            if not any(m.get("is_saved") is not False and m.get("map_id") != map_id for m in map_list):
                raise ServiceValidationError(f"{call.service}: '{names.get(map_id)}' is the only saved map; the "
                                             "robot needs one to restore a backup onto")
            if (coord.pending_restore or {}).get("map_id") == map_id:
                raise ServiceValidationError(f"{call.service}: a restore for this map is still being finished; "
                                             "try again in a few minutes")
            try:
                code = await _read(hass, call, coord.client.delete_map, map_id)
                _, after = await _read(hass, call, coord.client.get_map_info)
            finally:
                await coord.async_request_map_refresh()
        if code != 0 or any(m.get("map_id") == map_id for m in after):
            raise HomeAssistantError(f"{call.service}: the robot did not delete '{names.get(map_id)}' (error {code})")
        if (coord.pending_restore or {}).get("map_id") == map_id:
            coord._drop_restore(coord.pending_restore)
        return {"map_id": map_id, "map_name": names.get(map_id), "deleted": True}

    async def handle_fetch_cloud_map_backups(call: ServiceCall) -> ServiceResponse:
        import uuid

        from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

        from .cloud import CloudError, fetch_backups
        coord = _one(hass, call)
        if coord.entry is None:
            raise ServiceValidationError(f"{call.service}: no config entry")
        folder = setup_apply.backups_folder(hass, coord)
        terminal = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DOMAIN}:{coord.entry.entry_id}"))
        try:
            return await hass.async_add_executor_job(
                fetch_backups, coord.client, coord.entry.data[CONF_USERNAME], coord.entry.data[CONF_PASSWORD],
                terminal, folder, not coord.busy, call.data.get("verification_code"))
        except CloudError as exc:
            raise HomeAssistantError(f"{call.service}: {exc}") from exc
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: {type(exc).__name__}: {exc}") from exc

    async def _setup_map_id(call: ServiceCall, coord: TapoCoordinator) -> tuple[int, dict]:
        """(map_id, names) for a map-setup call: the 'map' field (name or id), else active."""
        names = await _read(hass, call, coord.map_names)
        ref = call.data.get("map")
        if ref in (None, ""):
            return coord.map_id, names
        from .mapdata import fold
        wanted = fold(str(ref).strip())
        hits = [mid for mid, n in names.items() if str(mid) == wanted or fold(n) == wanted]
        if len(hits) != 1:
            raise ServiceValidationError(
                f"{call.service}: no unique map matching '{ref}'. Available: {sorted(names.values())}")
        return hits[0], names

    from . import setup_apply

    def _robot_state(coord: TapoCoordinator, map_id: int) -> tuple[dict, list, list]:
        return setup_apply.robot_state(coord.client, map_id)

    def _find_snapshot(coord: TapoCoordinator, map_id: int | None, ref) -> dict | None:
        return setup_apply.find_snapshot(setup_apply.snapshot_folders(hass, coord), map_id, ref)

    async def handle_copy_map(call: ServiceCall) -> ServiceResponse:
        """Copy a map to a new map: back it up to the TP-Link cloud, download that backup,
        give it a fresh map id (mapbackup.reid_bkmap) and restore it under the given name. The
        original is never written to."""
        import hashlib
        import os
        import secrets
        import time
        import uuid as _uuid

        from homeassistant.components.network import async_get_source_ip
        from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

        from .cloud import fetch_backups
        from .map_restore import async_setup_map_restore
        coord = _one(hass, call)
        if coord.entry is None:
            raise ServiceValidationError(f"{call.service}: no config entry")
        names = await _read(hass, call, coord.map_names)
        ref = call.data.get("map")
        src = _match_map(call, names, ref, exact=True) if ref not in (None, "") else coord.map_id
        new_name = _new_map_name(call, names, call.data.get("name"))
        if coord.map_busy:
            raise ServiceValidationError(f"{call.service}: {coord.device_name} must be docked and idle")
        if coord.map_lock.locked():
            raise ServiceValidationError(f"{call.service}: a map write is running; try again shortly")
        started = time.time()
        async with coord.map_lock:
            _, map_list = await _read(hass, call, coord.client.get_map_info)
            if not any(m.get("map_id") == src and m.get("is_saved") is not False for m in map_list):
                raise ServiceValidationError(f"{call.service}: only a saved map can be copied")
            # 1. Back the source map up to the cloud (the only place the robot can put one).
            code = await _read(hass, call, coord.client.backup_map, src)
            if code != 0:
                raise HomeAssistantError(f"{call.service}: the robot refused to back up "
                                         f"'{names[src]}' (error {code})")
            status = None
            for _ in range(60):
                await asyncio.sleep(2)
                try:
                    process = await hass.async_add_executor_job(coord.client.get_map_br_process)
                except Exception as exc:
                    _LOGGER.debug("getMapBRProcess failed while backing up %s: %s", src, exc)
                    continue
                if _opt_int(process.get("type")) == 1 and process.get("status") in (3, 13, "3", "13"):
                    status = _opt_int(process.get("status"))
                    break
            if status != 3:
                raise HomeAssistantError(
                    f"{call.service}: the robot did not finish backing up '{names[src]}'"
                    + (" (it reported a failure)" if status == 13 else " (timed out waiting)"))
            # 2. Download it.
            terminal = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{DOMAIN}:{coord.entry.entry_id}"))
            try:
                got = await hass.async_add_executor_job(
                    fetch_backups, coord.client, coord.entry.data[CONF_USERNAME], coord.entry.data[CONF_PASSWORD],
                    terminal, setup_apply.backups_folder(hass, coord), False, call.data.get("verification_code"))
            except Exception as exc:
                raise HomeAssistantError(f"{call.service}: {exc}") from exc
            if got.get("status") == "code_sent":
                raise ServiceValidationError(f"{call.service}: TP-Link emailed a verification code; run "
                                             "copy_map again with verification_code set to it")
            # Only the backup just made (cloud timestamps are seconds; a few minutes' slack for clocks).
            mine = [b for b in got.get("backups", []) if b.get("map_id") == src and b.get("file")
                    and not b.get("error") and (_opt_int(b.get("timestamp")) or 0) >= started - 300]
            if not mine:
                raise HomeAssistantError(f"{call.service}: the cloud does not have the new backup of "
                                         f"'{names[src]}' yet; try again in a minute")
            newest = max(mine, key=lambda b: b.get("timestamp") or 0)
            folder = setup_apply.backups_folder(hass, coord)
            path = os.path.join(folder, newest["file"])

            def _reid_and_write() -> tuple[int, str]:
                with open(path, "rb") as fh:
                    data = fh.read()
                new_id = mapcopy.new_map_id(names, time.time())
                new_data = mapbackup.reid_bkmap(data, new_id)
                out_path = os.path.join(folder, f"cloud_{new_id}_{int(time.time())}.bin")
                with open(out_path, "wb") as fh:
                    fh.write(new_data)
                return new_id, out_path

            try:
                new_id, new_path = await hass.async_add_executor_job(_reid_and_write)
            except ValueError as exc:
                raise HomeAssistantError(f"{call.service}: could not prepare the copy: {exc}") from exc
            # 3. Restore it as a new map (the fresh id never matches one already on the robot).
            md5 = await hass.async_add_executor_job(
                lambda: hashlib.md5(open(new_path, "rb").read()).hexdigest())  # noqa: SIM115
            base = call.data.get("base_url")
            if base:
                base = str(base).rstrip("/")
            else:
                ip = await async_get_source_ip(hass, coord.client.host)
                scheme = "https" if hass.http.ssl_certificate else "http"
                base = f"{scheme}://{ip}:{hass.http.server_port}"
            store = async_setup_map_restore(hass)
            token = secrets.token_urlsafe(24)
            store[token] = new_path
            url = f"{base}/api/tapo_rv30/bkmap/{token}"
            process = {}
            try:
                try:
                    code = await hass.async_add_executor_job(coord.client.recover_map, new_id, md5, url)
                except RuntimeError as exc:
                    raise HomeAssistantError(f"{call.service}: {exc}") from exc
                if code != 0:
                    raise HomeAssistantError(f"{call.service}: the robot refused the copy (error {code})")
                misses = 0
                for _ in range(45):
                    await asyncio.sleep(2)
                    try:
                        process = await hass.async_add_executor_job(coord.client.get_map_br_process)
                        misses = 0
                    except Exception as exc:
                        misses += 1
                        _LOGGER.debug("getMapBRProcess failed (%s), %d in a row", exc, misses)
                        if misses >= 5:
                            break
                        continue
                    if process.get("status") in (3, 13, "3", "13"):
                        break
            finally:
                await asyncio.sleep(3)
                store.pop(token, None)
            status = _opt_int(process.get("status"))
            if status != 3:
                raise HomeAssistantError(
                    f"{call.service}: the robot did not finish copying '{names[src]}'"
                    + (" (it reported a failure)" if status == 13 else " (still applying when polling ended)"))
            save_code = 1
            try:
                current, _ = await _read(hass, call, coord.client.get_map_info)
                if current != new_id:
                    await _send(hass, call, coord.client.set_current_map, new_id)
                save_code = await _read(hass, call, coord.client.save_current_map, new_name)
            finally:
                await coord.async_request_map_refresh()
        if save_code:
            raise HomeAssistantError(f"{call.service}: the robot copied the map but did not save it as "
                                     f"'{new_name}' (error {save_code})")
        return {"map_id": new_id, "name": new_name, "source_map_id": src, "source_map_name": names.get(src),
                "backup": newest["file"]}

    async def handle_save_map_setup(call: ServiceCall) -> ServiceResponse:
        import json
        import os
        import time

        from . import mapsnapshot
        coord = _one(hass, call)
        map_id, names = await _setup_map_id(call, coord)
        data, presets, schedules = await _read(hass, call, _robot_state, coord, map_id)
        snap = mapsnapshot.build(map_id, names.get(map_id), data.get("area_list", []),
                                 data.get("furniture_list", []), presets, schedules,
                                 time.strftime("%Y-%m-%dT%H:%M:%S"))
        folder = setup_apply.snapshots_folder(hass, coord)

        def _write() -> bool:
            """Write the snapshot; the latest copy is only replaced by a degraded one
            (rooms missing or unnamed, as after a lost map) when forced."""
            os.makedirs(os.path.join(folder, "history"), exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            latest = os.path.join(folder, f"{map_id}.json")
            old = None
            for path in (latest, os.path.join(os.path.dirname(folder), f"{map_id}.json")):
                if old is None:
                    try:
                        with open(path) as fh:
                            old = json.load(fh)
                    except (OSError, ValueError):
                        pass
            keep_old = mapsnapshot.is_degraded(old, snap) and not call.data.get("force")
            paths = [os.path.join(folder, "history", f"{map_id}_{stamp}.json")]
            if not keep_old:
                paths.append(latest)
            for path in paths:
                setup_apply.write_json(path, snap)
            return keep_old

        kept = await hass.async_add_executor_job(_write)
        if kept:
            raise ServiceValidationError(
                f"{call.service}: map {names.get(map_id) or map_id} looks degraded (rooms missing or "
                "unnamed), so the saved setup was kept and this one only went to history. "
                "Pass force: true to replace it anyway.")
        return {"map_id": map_id, "map_name": names.get(map_id), "saved": snap["counts"],
                "furniture": len(snap["furniture"]), "presets": len(snap["presets"]),
                "schedules": len(snap["schedules"]), "file": os.path.relpath(os.path.join(folder, f"{map_id}.json"), hass.config.path(DOMAIN))}

    async def handle_apply_map_setup(call: ServiceCall) -> ServiceResponse:
        coord = _one(hass, call)
        dry_run = bool(call.data.get("dry_run"))
        if not dry_run and not call.data.get("confirm"):
            raise ServiceValidationError(
                f"{call.service}: this writes rooms, zones, furniture, presets and schedules; "
                "set confirm: true (or dry_run: true to see what it would do)")
        if coord.map_busy and not dry_run:
            raise ServiceValidationError(f"{call.service}: {coord.device_name} must be docked and idle")
        map_id, names = await _setup_map_id(call, coord)
        src = call.data.get("source_map")
        snap = await hass.async_add_executor_job(_find_snapshot, coord, map_id, src)
        if snap is None:
            where = f"matching source_map '{src}'" if src else f"for map {map_id}"
            raise ServiceValidationError(f"{call.service}: no saved setup {where}; run save_map_setup first")
        try:
            result = await setup_apply.apply_setup(hass, coord, map_id, snap, dry_run)
        except setup_apply.MapBusy as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from exc
        except setup_apply.ApplyError as exc:
            raise HomeAssistantError(f"{call.service}: {exc}") from exc
        except Exception as exc:
            raise HomeAssistantError(f"{call.service}: could not read the map from the vacuum: {exc}") from exc
        result["map_name"] = names.get(map_id)
        return result

    async def handle_restore_map_backup(call: ServiceCall) -> ServiceResponse:
        """Restore a map backup to the robot. By default HA serves the backup it already holds
        on a short-lived LAN URL and the robot fetches and applies it - a fully local restore,
        no cloud. use_cloud_url hands the robot the backup's own TP-Link URL instead, for when
        the robot cannot reach HA on the LAN."""
        import asyncio
        import hashlib
        import os
        import secrets

        from homeassistant.components.network import async_get_source_ip

        from .map_restore import async_setup_map_restore
        coord = _one(hass, call)
        if not call.data.get("confirm"):
            raise ServiceValidationError(f"{call.service}: this overwrites a map on the robot; set confirm: true")
        if coord.map_busy:
            raise ServiceValidationError(f"{call.service}: {coord.device_name} must be docked and idle")
        import re

        from . import mapsnapshot
        folders = setup_apply.backup_folders(hass, coord)
        names = await _read(hass, call, coord.map_names)
        new_name_val = call.data.get("new_name")
        if new_name_val not in (None, "") and call.data.get("use_cloud_url"):
            raise ServiceValidationError(f"{call.service}: new_name restores from the copy Home Assistant "
                                         "holds; it cannot be combined with use_cloud_url")
        new_name_clean = _new_map_name(call, names, new_name_val) if new_name_val not in (None, "") else None
        ref, fname = call.data.get("map"), call.data.get("file")
        # Which map the backup belongs to. It may no longer exist on the robot (the lost-map
        # case), so beyond the robot's own maps, accept a bare map id, a saved setup's map
        # name, or the id in the backup file's name.
        backup_id = None
        snap_name = None
        if ref not in (None, ""):
            want = fold(str(ref).strip())
            hits = [mid for mid, n in names.items() if str(mid) == want or fold(n) == want]
            if len(hits) > 1:
                raise ServiceValidationError(f"{call.service}: '{ref}' matches several maps: {sorted(names.values())}")
            if hits:
                backup_id = hits[0]
            elif want.isdigit():
                backup_id = int(want)
            else:
                snap = await hass.async_add_executor_job(_find_snapshot, coord, None, ref)
                if snap:
                    backup_id, snap_name = snap.get("map_id"), snap.get("map_name")
        if backup_id is None and fname:
            m = re.match(r"^(?:cloud|local)_(\d+)_\d+\.(?:bin|bkmap)$", os.path.basename(str(fname)))
            if m:
                backup_id = int(m.group(1))
        if backup_id is None and ref in (None, ""):
            backup_id = coord.map_id
        if backup_id is None:
            raise ServiceValidationError(
                f"{call.service}: no map matching '{ref}' on the robot or in the saved map setups; "
                f"pass the map id or file: (robot maps: {sorted(names.values())})")
        try:
            map_id, carrier = mapsnapshot.restore_target(names, coord.map_id, backup_id)
        except ValueError as exc:
            raise ServiceValidationError(f"{call.service}: {exc}") from exc

        def _pick() -> str | None:
            # This robot's own backups first, then the shared folder older versions used.
            if fname:
                return backupstore.locate(folders, os.path.basename(str(fname)))
            # cloud_<map_id>_<timestamp>.bin only - never the _snapshot preview image.
            pat = re.compile(rf"^cloud_{backup_id}_\d+\.bin$")
            for folder in folders:
                try:
                    cands = sorted(f for f in os.listdir(folder) if pat.match(f))
                except OSError:      # no backups fetched yet
                    continue
                if cands:
                    return os.path.join(folder, cands[-1])
            return None

        # Default: serve the backup from HA on the LAN and let the robot fetch it directly - a
        # fully local restore, no cloud. The robot's HTTP client needs a clean Content-Length
        # response, so the URL must be HA's direct LAN address: a reverse proxy in front of HA
        # that serves the body chunked makes the robot's download stall near the end and fail.
        # base_url overrides the auto-derived address; use_cloud_url hands the robot the backup's
        # own TP-Link URL instead, for when it cannot reach HA on the LAN.
        store = None
        token = None
        src = "local"
        if call.data.get("use_cloud_url"):
            import uuid as _uuid

            from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

            from .cloud import _connect
            terminal = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{DOMAIN}:{coord.entry.entry_id}"))

            def _cloud_backup() -> dict | None:
                cloud, thing = _connect(coord.client, coord.entry.data[CONF_USERNAME],
                                        coord.entry.data[CONF_PASSWORD], terminal,
                                        call.data.get("verification_code"))
                best = None
                for b in cloud.map_backups(thing):
                    if b.get("mapId") == backup_id and (best is None
                            or (b.get("timestamp") or 0) > (best.get("timestamp") or 0)):
                        best = b
                return best

            best = await hass.async_add_executor_job(_cloud_backup)
            if not best or not best.get("mapUrl"):
                raise ServiceValidationError(f"{call.service}: no cloud backup for map {backup_id}")
            url = best["mapUrl"]
            md5 = best.get("mapMd5")
            src = "cloud"
        else:
            path = await hass.async_add_executor_job(_pick)
            if path is None:
                raise ServiceValidationError(
                    f"{call.service}: no backup file for map {backup_id} in {folders[0]}; "
                    "run fetch_cloud_map_backups first, or pass file:")
            if new_name_clean is not None:
                # Restore as a new map: give the backup a fresh id first (mapbackup.reid_bkmap)
                # so it lands beside the original instead of overwriting its carrier. A fresh id
                # never matches one already on the robot, so no carrier is needed.
                def _reid_local(src_path=path) -> tuple[int, str]:
                    with open(src_path, "rb") as fh:
                        data = fh.read()
                    new_id = mapcopy.new_map_id(names, time.time())
                    new_data = mapbackup.reid_bkmap(data, new_id)
                    out_path = os.path.join(os.path.dirname(src_path), f"cloud_{new_id}_{int(time.time())}.bin")
                    with open(out_path, "wb") as fh:
                        fh.write(new_data)
                    return new_id, out_path
                import time
                try:
                    backup_id, path = await hass.async_add_executor_job(_reid_local)
                except ValueError as exc:
                    raise ServiceValidationError(
                        f"{call.service}: could not prepare a new map from that backup: {exc}") from exc
                map_id, carrier = backup_id, False
            md5 = await hass.async_add_executor_job(
                lambda: hashlib.md5(open(path, "rb").read()).hexdigest())  # noqa: SIM115
            base = call.data.get("base_url")
            if base:
                base = str(base).rstrip("/")
            else:
                ip = await async_get_source_ip(hass, coord.client.host)
                scheme = "https" if hass.http.ssl_certificate else "http"
                base = f"{scheme}://{ip}:{hass.http.server_port}"
            store = async_setup_map_restore(hass)
            token = secrets.token_urlsafe(24)
            store[token] = path
            url = f"{base}/api/tapo_rv30/bkmap/{token}"
        process: dict = {}
        if carrier:
            # Recorded before the robot is asked, so a Home Assistant restart while it applies the
            # backup still finishes it; dropped again if the robot refuses or fails it.
            coord.expect_restore(backup_id, names.get(backup_id) or snap_name, map_id)
        pend = coord.pending_restore if carrier else None
        try:
            try:
                code = await hass.async_add_executor_job(coord.client.recover_map, map_id, md5, url)
            except RuntimeError as exc:
                if pend is not None:
                    coord._drop_restore(pend)
                raise HomeAssistantError(f"{call.service}: {exc}") from exc
            if code != 0 and pend is not None:
                coord._drop_restore(pend)
            if code != 0:
                process = {"status": 13}
                raise HomeAssistantError(f"{call.service}: robot refused the map restore (error code {code})")
            misses = 0
            for _ in range(45):
                await asyncio.sleep(2)
                try:
                    process = await hass.async_add_executor_job(coord.client.get_map_br_process)
                    misses = 0
                except Exception as exc:
                    # The robot is busy unpacking; one missed read is not a failed restore.
                    misses += 1
                    _LOGGER.debug("getMapBRProcess failed (%s), %d in a row", exc, misses)
                    if misses >= 5:
                        break
                    continue
                # status 2 is "still running": wait for success (3) or failure (13).
                if process.get("status") in (3, 13, "3", "13"):
                    break
        finally:
            if store is not None and token is not None:
                if _opt_int(process.get("status")) in (None, 2):
                    # Still applying (or unknown): keep serving the backup for a while longer.
                    hass.loop.call_later(600, store.pop, token, None)
                else:
                    await asyncio.sleep(3)  # let a slow fetch finish before the URL stops serving
                    store.pop(token, None)
        # The restore can take minutes; if the entry was reloaded meanwhile, carry on with its
        # new coordinator (the old one's client is closed and its pending restore is lost).
        coord = hass.data.get(DOMAIN, {}).get(coord.entry.entry_id, coord) if coord.entry else coord
        await coord.async_request_map_refresh()
        status = _opt_int(process.get("status"))
        if status == 13 and pend is not None and (coord.pending_restore or {}).get("map_id") == backup_id:
            coord._drop_restore(coord.pending_restore)
        # Where did it land? The robot restores under the backup's own map id; if that id was
        # gone it comes back as a new, unsaved map that must be saved in the Tapo app.
        landed = None
        if status == 3:
            try:
                _, map_list = await hass.async_add_executor_job(coord.client.get_map_info)
                landed = next((m for m in map_list if m.get("map_id") == backup_id), None)
            except Exception:  # the restore itself already succeeded
                landed = None
        saved = bool(landed) and landed.get("is_saved", True) is not False
        if new_name_clean is not None and status == 3 and landed is not None and not saved:
            # Restore-as-new: save it under the chosen name straight away instead of asking the
            # Tapo app to do it (a fresh id is never a lost map someone has to recognise).
            try:
                cur, _ = await hass.async_add_executor_job(coord.client.get_map_info)
                if cur != map_id:
                    await hass.async_add_executor_job(coord.client.set_current_map, map_id)
                save_code = await hass.async_add_executor_job(coord.client.save_current_map, new_name_clean)
                if not save_code:
                    saved = True
            except Exception as exc:
                _LOGGER.warning("Could not save the new map '%s' after restore: %s", new_name_clean, exc)
        # The robot reports status 3 when the map is applied, 13 on failure, 2 while still working.
        note = ("restore failed on the robot (status 13); if the backup is served through a reverse "
                "proxy, set base_url to HA's direct LAN address" if status == 13
                else "still applying when polling ended" if status == 2 else None)
        next_steps = None
        if status in (2, None) and carrier and code == 0:
            # Polling ended before the robot finished; it will most likely land, so watch for it
            # (the watcher only acts once the map shows up and is saved).
            label = names.get(backup_id) or snap_name
            coord.expect_restore(backup_id, label, map_id)
            next_steps = ("The robot is still applying the backup. Once the map appears, save it in the Tapo app"
                          + (f" as \"{label}\"" if label else "") + "; Home Assistant then puts back its "
                          "room names, zones, furniture, presets and schedules by itself.")
        elif status == 3 and landed and carrier:
            # The map had been deleted: finish it automatically once it is saved in the app.
            label = names.get(backup_id) or snap_name
            coord.expect_restore(backup_id, label, map_id)
            next_steps = (("The map came back as a new, unsaved map. Save it in the Tapo app"
                           + (f" as \"{label}\"" if label else "") + ". Home Assistant then puts back its room "
                           "names, no-go zones, furniture, presets and schedules by itself and lets you know.")
                          if not saved else
                          "Home Assistant is putting back its room names, zones, furniture, presets and schedules.")
        elif status == 3 and landed and not saved and new_name_clean is None:
            next_steps = (f"The map came back as a new, unsaved map (id {backup_id}). Save it in the Tapo app "
                          "(keep the name), then run apply_map_setup on it to put back room names, no-go zones, "
                          "furniture, presets and schedules.")
        elif status == 3:
            next_steps = ("Run apply_map_setup on this map (dry_run: true first to preview) to put back anything "
                          "the backup does not carry: room names, zones, furniture, presets, schedules.")
        return {"map_id": map_id, "map_name": names.get(map_id), "backup_map_id": backup_id,
                "backup_map_name": names.get(backup_id) or snap_name, "carrier": carrier,
                "restored_map_saved": saved if status == 3 else None, "source": src, "md5": md5,
                "url": url, "error_code": code, "process": process, "applied": status == 3,
                "new_name": new_name_clean, "note": note, "next_steps": next_steps}

    hass.services.async_register(DOMAIN, "restore_map_backup", _admin_only(hass, handle_restore_map_backup),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "save_map_setup", _admin_only(hass, handle_save_map_setup),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "apply_map_setup", _admin_only(hass, handle_apply_map_setup),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "fetch_cloud_map_backups", _admin_only(hass, handle_fetch_cloud_map_backups),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "clean_rooms", handle_clean_rooms)
    hass.services.async_register(DOMAIN, "run_preset", handle_run_preset)
    for name, fn in (("create_preset", handle_create_preset), ("update_preset", handle_update_preset),
                     ("delete_preset", handle_delete_preset)):
        if name in ADMIN_SERVICES:
            fn = _admin_only(hass, fn)
        hass.services.async_register(DOMAIN, name, fn, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "set_map", handle_set_map)
    hass.services.async_register(DOMAIN, "rename_map", _admin_only(hass, handle_rename_map),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "set_map_lock", _admin_only(hass, handle_set_map_lock),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "delete_map", _admin_only(hass, handle_delete_map),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "copy_map", _admin_only(hass, handle_copy_map),
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "go_to", handle_go_to)
    hass.services.async_register(DOMAIN, "remote_drive", handle_remote_drive,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "add_schedule", handle_add_schedule,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "set_schedule", handle_set_schedule)
    hass.services.async_register(DOMAIN, "remove_schedule", _admin_only(hass, handle_remove_schedule))
    hass.services.async_register(DOMAIN, "remove_matter_fabric", _admin_only(hass, handle_remove_matter_fabric))
    hass.services.async_register(DOMAIN, "get_matter_setup_code", _admin_only(hass, handle_get_matter_setup_code),
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "get_clean_records", handle_get_clean_records,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "set_room_settings", handle_set_room_settings)
    hass.services.async_register(DOMAIN, "clean_zone", handle_clean_zone)
    hass.services.async_register(DOMAIN, "get_zone_presets", handle_get_zone_presets,
                                 supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "run_zone_preset", handle_run_zone_preset)
    for name, fn in (("create_zone_preset", handle_create_zone_preset),
                     ("update_zone_preset", handle_update_zone_preset),
                     ("delete_zone_preset", handle_delete_zone_preset)):
        hass.services.async_register(DOMAIN, name, _admin_only(hass, fn),
                                     supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "run_schedule", handle_run_schedule)
    hass.services.async_register(DOMAIN, "send_raw", _admin_only(hass, handle_send_raw),
                                 supports_response=SupportsResponse.ONLY)


def _zone_restore_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.pending_zone_restore")


def _zone_restore_snapshots(raw: dict | None) -> dict[str, dict]:
    """Read the per-map format and migrate the original single-map record in memory."""
    if not raw:
        return {}
    if "map_id" in raw and "areas" in raw:  # legacy b1 snapshot written before per-map tracking
        return {str(raw["map_id"]): {"map_id": raw["map_id"], "areas": raw["areas"]}}
    return dict(raw.get("maps") or {})


async def _zone_restore_get(hass: HomeAssistant, entry_id: str, map_id: int) -> list[dict] | None:
    raw = await _zone_restore_store(hass, entry_id).async_load()
    pending = _zone_restore_snapshots(raw).get(str(map_id))
    return pending.get("areas") if pending else None


async def _zone_restore_put(hass: HomeAssistant, entry_id: str, map_id: int, areas: list[dict]) -> None:
    store = _zone_restore_store(hass, entry_id)
    lock = _ZONE_RESTORE_STORAGE_LOCKS.setdefault(entry_id, asyncio.Lock())
    async with lock:
        maps = _zone_restore_snapshots(await store.async_load())
        maps.setdefault(str(map_id), {"map_id": map_id, "areas": areas})
        await store.async_save({"maps": maps})


async def _zone_restore_drop(hass: HomeAssistant, entry_id: str, map_id: int) -> None:
    store = _zone_restore_store(hass, entry_id)
    lock = _ZONE_RESTORE_STORAGE_LOCKS.setdefault(entry_id, asyncio.Lock())
    async with lock:
        maps = _zone_restore_snapshots(await store.async_load())
        maps.pop(str(map_id), None)
        if maps:
            await store.async_save({"maps": maps})
        else:
            await store.async_remove()


def _schedule_zone_restore(hass: HomeAssistant, entry_id: str, map_id: int,
                           saved_areas: list[dict]) -> None:
    key = (entry_id, map_id)
    existing = _ZONE_RESTORE_TASKS.get(key)
    if existing is not None and not existing.done():
        return
    task = hass.async_create_task(_restore_zone_areas_after_clean(hass, entry_id, map_id, saved_areas))
    _ZONE_RESTORE_TASKS[key] = task
    task.add_done_callback(lambda done, k=key: _ZONE_RESTORE_TASKS.pop(k, None)
                           if _ZONE_RESTORE_TASKS.get(k) is done else None)


async def _restore_zone_areas_after_clean(hass: HomeAssistant, entry_id: str, map_id: int,
                                          saved_areas: list[dict]) -> None:
    """Wait for cleaning to finish, restore saved areas, and retain pending state on errors."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    active_seen = False
    inactive_since = None
    while True:
        coord = hass.data.get(DOMAIN, {}).get(entry_id)
        if coord is None:
            return
        delay = max(5, min(coord.poll_interval, 30))
        active = coord.status_code in CLEANING_CODES or coord.status_code in PAUSED_CODES or coord.status_code == 4
        if active:
            active_seen = True
            inactive_since = None
        elif active_seen:
            inactive_since = inactive_since or loop.time()
            if loop.time() - inactive_since >= 15:
                break
        elif loop.time() - started >= 90:
            break
        await asyncio.sleep(delay)
    while True:
        coord = hass.data.get(DOMAIN, {}).get(entry_id)
        if coord is None:
            return
        delay = max(5, min(coord.poll_interval, 30))
        if coord.status_code in CLEANING_CODES or coord.status_code in PAUSED_CODES or coord.status_code == 4:
            await asyncio.sleep(delay)
            continue
        try:
            result = await hass.async_add_executor_job(coord.client.set_areas, map_id, "area", saved_areas)
            if result in (None, 0):
                await coord.async_request_map_refresh()
                await _zone_restore_drop(hass, entry_id, map_id)
                return
            _LOGGER.warning("Robot rejected the post-clean temporary-zone restore for map %s (error %s); will retry", map_id, result)
        except Exception as exc:
            _LOGGER.warning("Could not restore saved map zones for map %s; will retry: %s", map_id, exc)
        await asyncio.sleep(delay)

async def async_resume_zone_restore(hass: HomeAssistant, coordinator: TapoCoordinator) -> None:
    """Resume persisted temporary-zone cleanups after the integration entry loads."""
    entry_id = coordinator.entry.entry_id
    store = _zone_restore_store(hass, entry_id)
    snapshots = _zone_restore_snapshots(await store.async_load())
    for raw_map_id, pending in snapshots.items():
        try:
            map_id = int(raw_map_id)
            areas = pending["areas"]
        except (TypeError, KeyError, ValueError):
            continue
        if isinstance(areas, list):
            _schedule_zone_restore(hass, entry_id, map_id, areas)

def cancel_zone_restore_tasks(entry_id: str) -> None:
    """Cancel pending map-area restores when a config entry unloads."""
    for key, task in tuple(_ZONE_RESTORE_TASKS.items()):
        if key[0] == entry_id:
            task.cancel()
            _ZONE_RESTORE_TASKS.pop(key, None)


def async_unload_services(hass: HomeAssistant) -> None:
    """Remove the services once the last config entry is gone."""
    for svc in SERVICES:
        hass.services.async_remove(DOMAIN, svc)
