"""Websocket commands for the sidebar page's map editor.

tapo_rv30/map/edit_get    {entity_id, map_id?}   -> the editable layers of a map (world mm)
tapo_rv30/map/edit_apply  {entity_id, map_id, areas?, furniture?, rooms?, order?} -> write them

Only the editable layers are touched (no-go zones, virtual walls, carpets, furniture, room
names and order). The map's shape (grid) is the robot's own and is never written.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, FURNITURE_TYPES
from .mapdata import b64name, vertexs_match

_LOGGER = logging.getLogger(__name__)

_KEY = f"{DOMAIN}_map_edit_ws"
_AREA_TYPES = ("forbid", "virtual_wall", "carpet_rectangle", "carpet_round")
_KEEP = ("label", "define_type", "carpet_strategy")   # robot fields the editor does not round-trip


def _coord(hass: HomeAssistant, entity_id: str):
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)


def async_setup_map_edit_ws(hass: HomeAssistant) -> None:
    if hass.data.get(_KEY):
        return
    hass.data[_KEY] = True
    websocket_api.async_register_command(hass, ws_edit_get)
    websocket_api.async_register_command(hass, ws_edit_apply)


@websocket_api.websocket_command({
    vol.Required("type"): "tapo_rv30/map/edit_get",
    vol.Required("entity_id"): str,
    vol.Optional("map_id"): int,
})
@websocket_api.async_response
async def ws_edit_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coord = _coord(hass, msg["entity_id"])
    if coord is None:
        connection.send_error(msg["id"], "not_found", f"No Tapo vacuum for {msg['entity_id']}")
        return
    map_id = msg.get("map_id") or coord.map_id
    try:
        data = await hass.async_add_executor_job(coord.client.get_map_data, map_id)
    except Exception as exc:
        connection.send_error(msg["id"], "read_failed", str(exc))
        return
    areas = {t: [] for t in _AREA_TYPES}
    rooms = []
    for a in data.get("area_list", []):
        t = a.get("type")
        if t in areas:
            areas[t].append({"id": a.get("id"), "vertexs": a.get("vertexs")})
        elif t == "room":
            rooms.append({"id": a.get("id"), "name": b64name(a.get("name", "")),
                          "vertexs": a.get("vertexs")})
    connection.send_result(msg["id"], {
        "map_id": map_id,
        "areas": areas,
        "furniture": data.get("furniture_list", []),
        "furniture_types": {str(k): v for k, v in FURNITURE_TYPES.items()},
        "rooms": rooms,
    })


@websocket_api.websocket_command({
    vol.Required("type"): "tapo_rv30/map/edit_apply",
    vol.Required("entity_id"): str,
    vol.Required("map_id"): int,
    vol.Optional("areas"): dict,
    vol.Optional("furniture"): list,
    vol.Optional("rooms"): list,
    vol.Optional("order"): list,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_edit_apply(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    coord = _coord(hass, msg["entity_id"])
    if coord is None:
        connection.send_error(msg["id"], "not_found", f"No Tapo vacuum for {msg['entity_id']}")
        return
    if coord.map_busy:
        connection.send_error(msg["id"], "busy", f"{coord.device_name} must be docked and idle to edit the map")
        return
    if coord.map_lock.locked():
        connection.send_error(msg["id"], "busy", f"Another map write to {coord.device_name} is still running")
        return
    async with coord.map_lock:     # one map write per robot at a time (each switches maps)
        # Asked live: the last poll may predate the robot's own schedule starting it.
        try:
            working = await coord._robot_working()
        except Exception as exc:
            connection.send_error(msg["id"], "status_failed",
                                  f"Could not confirm that {coord.device_name} is idle: {exc}")
            return
        if working:
            connection.send_error(msg["id"], "busy", f"{coord.device_name} is working; edit the map once it is "
                                  "docked and idle")
            return
        map_id = msg["map_id"]
        result: dict[str, Any] = {}
        previous = None
        try:
            # setAreaInfo writes the active map; switch to the target first (and back after).
            info = await hass.async_add_executor_job(coord.client.send, "getMapInfo")
            current = (info.get("result") or {}).get("current_map_id")
            if current != map_id:
                previous = current
                await hass.async_add_executor_job(coord.client.set_current_map, map_id)
            # The editor only round-trips id and shape; keep the robot's own fields (label,
            # define_type, carpet handling) on zones it already has, or the save would drop them.
            existing = {}
            if msg.get("areas"):
                data = await hass.async_add_executor_job(coord.client.get_map_data, map_id)
                existing = {(a.get("type"), a.get("id")): a for a in data.get("area_list", [])}
            for t, items in (msg.get("areas") or {}).items():
                if t in _AREA_TYPES:
                    items = [{**{k: old[k] for k in _KEEP if k in old}, **item}
                             if (old := existing.get((t, item.get("id")))) else item
                             for item in items]
                    result[t] = await hass.async_add_executor_job(coord.client.set_areas, map_id, t, items)
            if "furniture" in msg:
                result["furniture"] = await hass.async_add_executor_job(
                    coord.client.set_furniture, map_id, msg["furniture"])
                # The robot can answer error_code 0 for setFurnitureInfo without actually
                # keeping the change (seen in the field: furniture stays in the editor's own
                # state but never reaches the rendered map) - and separately, it can keep an
                # existing item's id while silently ignoring an in-place update to it (a move
                # or a rotation), which an id-only check would not catch. Read the map straight
                # back and make sure every item we just sent is both still there and actually
                # at the shape/position we sent, before calling it saved.
                sent_by_id = {f.get("id"): f for f in msg["furniture"] if f.get("id") is not None}
                if sent_by_id:
                    check = await hass.async_add_executor_job(coord.client.get_map_data, map_id)
                    kept_by_id = {f.get("id"): f for f in check.get("furniture_list") or []}
                    missing = sorted(set(sent_by_id) - set(kept_by_id))
                    if missing:
                        raise RuntimeError(
                            f"the robot did not keep furniture {missing} (wrote ok, but a "
                            "read-back shows it missing — this looks like a firmware limitation, "
                            "not an editor bug)")
                    stale = sorted(fid for fid, sent in sent_by_id.items()
                                  if not vertexs_match(sent.get("vertexs"), kept_by_id[fid].get("vertexs")))
                    if stale:
                        raise RuntimeError(
                            f"the robot did not keep the new position/rotation for furniture {stale} "
                            "(wrote ok and the item is still there, but a read-back shows its old "
                            "shape — this looks like a firmware limitation updating existing "
                            "furniture in place, not an editor bug)")
            if msg.get("rooms"):
                # vertexs is echoed back unchanged (the editor never offers to reshape a room,
                # only to rename it) - set_areas replaces the whole room entry, and omitting
                # vertexs here would risk the robot clearing the room's boundary along with
                # whatever it does with a field it wasn't given.
                room_areas = [{"type": "room", "id": r["id"],
                               "name": base64.b64encode(str(r.get("name", "")).encode()).decode(),
                               **({"vertexs": r["vertexs"]} if r.get("vertexs") else {})}
                              for r in msg["rooms"] if r.get("id") is not None]
                result["rooms"] = await hass.async_add_executor_job(
                    coord.client.set_areas, map_id, "room", room_areas)
                # Same read-after-write distrust as furniture: a rename the robot
                # acknowledges but quietly leaves unchanged must not be reported as
                # saved - check both the name and (since it's sent too) the shape.
                sent_by_id = {r["id"]: r for r in msg["rooms"] if r.get("id") is not None}
                if sent_by_id:
                    check = await hass.async_add_executor_job(coord.client.get_map_data, map_id)
                    kept_by_id = {a.get("id"): a for a in check.get("area_list") or [] if a.get("type") == "room"}
                    stale_name = sorted(rid for rid, r in sent_by_id.items()
                                        if b64name(kept_by_id.get(rid, {}).get("name", "")) != r.get("name", ""))
                    if stale_name:
                        raise RuntimeError(
                            f"the robot did not keep the new name for room(s) {stale_name} (wrote ok, "
                            "but a read-back shows the old name — this looks like a firmware "
                            "limitation, not an editor bug)")
                    stale_shape = sorted(rid for rid, r in sent_by_id.items() if r.get("vertexs")
                                         and not vertexs_match(r["vertexs"], kept_by_id.get(rid, {}).get("vertexs")))
                    if stale_shape:
                        raise RuntimeError(
                            f"the robot changed the shape of room(s) {stale_shape} while only a "
                            "rename was sent (wrote ok, but a read-back shows a different "
                            "boundary — this looks like a firmware limitation, not an editor bug)")
            if msg.get("order"):
                result["order"] = await hass.async_add_executor_job(
                    coord.client.set_clean_order, map_id, msg["order"])
        except Exception as exc:
            _LOGGER.exception("Map editor save failed for %s on map %s", msg["entity_id"], msg["map_id"])
            detail = str(exc).strip() or repr(exc) or type(exc).__name__
            connection.send_error(msg["id"], "write_failed", detail)
            return
        finally:
            if previous is not None:      # leave the robot on the map it was using
                try:
                    await hass.async_add_executor_job(coord.client.set_current_map, previous)
                except Exception as exc:
                    _LOGGER.warning("Could not switch %s back to map %s: %s", coord.device_name, previous, exc)
    await coord.async_request_map_refresh()
    connection.send_result(msg["id"], {"map_id": map_id, "result": result})
