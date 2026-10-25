"""Websocket commands for the sidebar page's Log tab.

tapo_rv30/log/list   {entity_id, limit?}   -> recent records from this integration's own
                                              logger (custom_components.tapo_rv30 and its
                                              submodules: tpap, coordinator, services, ...),
                                              newest first.
tapo_rv30/log/clear  {entity_id}           -> empty the ring buffer.

The buffer is process-wide (one logger namespace for every configured robot), not per config
entry: entity_id is only used, as in backup_ws, to check the caller is naming a real Tapo
vacuum and to resolve its coordinator for a friendly error. The ring buffer itself lives in
logtail (pure, unit-tested); this is the thin Home Assistant layer over it.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import logtail
from .const import DOMAIN

_KEY = f"{DOMAIN}_log_ws"


def _coord(hass: HomeAssistant, entity_id: str):
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        return None
    return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)


def async_setup_log_ws(hass: HomeAssistant) -> None:
    if hass.data.get(_KEY):
        return
    hass.data[_KEY] = True
    websocket_api.async_register_command(hass, ws_log_list)
    websocket_api.async_register_command(hass, ws_log_clear)


@websocket_api.websocket_command({
    vol.Required("type"): "tapo_rv30/log/list",
    vol.Required("entity_id"): str,
    vol.Optional("limit"): int,
})
@websocket_api.async_response
async def ws_log_list(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    if _coord(hass, msg["entity_id"]) is None:
        connection.send_error(msg["id"], "not_found", f"No Tapo vacuum for {msg['entity_id']}")
        return
    handler = logtail.install()
    records = handler.list(msg.get("limit"))
    connection.send_result(msg["id"], {
        "records": [{**r, "when": logtail.human_time(r["time"])} for r in records],
        "capacity": handler.capacity,
        "logger": logtail.LOGGER_NAME,
    })


@websocket_api.websocket_command({
    vol.Required("type"): "tapo_rv30/log/clear",
    vol.Required("entity_id"): str,
})
@websocket_api.async_response
async def ws_log_clear(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    if _coord(hass, msg["entity_id"]) is None:
        connection.send_error(msg["id"], "not_found", f"No Tapo vacuum for {msg['entity_id']}")
        return
    logtail.install().clear()
    connection.send_result(msg["id"], {"cleared": True})
