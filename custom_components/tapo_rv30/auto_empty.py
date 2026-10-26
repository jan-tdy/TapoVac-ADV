"""Home Assistant owned schedule for the robot's Empty Bin action."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOCKED_CODES, DOMAIN

_LOGGER = logging.getLogger(__name__)
KEY = f"{DOMAIN}_auto_empty_ws"


class TapoAutoEmptyPlanner:
    """Persist a cadence and invoke the existing dust collection command when due and docked."""

    def __init__(self, hass: HomeAssistant, coordinator, entry) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.auto_empty")
        self.enabled = False
        self.interval_days = 1
        self.run_time = "10:00"
        self.next_run: float | None = None
        self.last_run: float | None = None
        self.last_error: str | None = None
        self.command_confirmed = False
        self._listeners: list[Callable[[], None]] = []
        self._unsub = None
        self._unsub_coordinator = None
        self._busy = False
        self._retry_at = 0.0

    async def async_load(self) -> None:
        saved = await self.store.async_load() or {}
        self.enabled = bool(saved.get("enabled", False))
        self.interval_days = max(1, min(30, int(saved.get("interval_days", 1))))
        self.run_time = str(saved.get("run_time", "10:00"))
        self.next_run = saved.get("next_run")
        self.last_run = saved.get("last_run")
        self.command_confirmed = bool(saved.get("command_confirmed", False))
        if self.enabled and self.next_run is None:
            self.next_run = self._next_after(dt_util.now())
            await self._save()

    def async_start(self) -> None:
        self._unsub = async_track_time_interval(self.hass, self._tick, timedelta(minutes=1))
        self._unsub_coordinator = self.coordinator.async_add_listener(self._notify)
        self.hass.async_create_task(self._tick(None))

    @callback
    def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        if self._unsub_coordinator:
            self._unsub_coordinator()
            self._unsub_coordinator = None

    @property
    def supported(self) -> bool:
        # A registered Empty Bin button is stronger evidence than the optional component
        # metadata: several non-Plus models accept the command without reporting that flag.
        entity_id = er.async_get(self.hass).async_get_entity_id(
            "button", DOMAIN, f"{self.entry.entry_id}_empty_bin")
        return (self.command_confirmed or entity_id is not None
                or (self.coordinator.has("dust_bucket") and "dust" in self.coordinator.settings))

    @property
    def view(self) -> dict[str, Any]:
        return {"supported": self.supported, "enabled": self.enabled, "interval_days": self.interval_days,
                "run_time": self.run_time, "next_run": self.next_run,
                "last_run": self.last_run, "last_error": self.last_error,
                "status_code": self.coordinator.status_code}

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def _save(self) -> None:
        await self.store.async_save({"enabled": self.enabled, "interval_days": self.interval_days,
                                     "run_time": self.run_time, "next_run": self.next_run,
                                     "last_run": self.last_run,
                                     "command_confirmed": self.command_confirmed})

    def _next_after(self, now: datetime, *, skip_today: bool = False) -> float:
        hour, minute = (int(part) for part in self.run_time.split(":"))
        candidate = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        if candidate <= now or skip_today:
            candidate += timedelta(days=self.interval_days)
        return candidate.timestamp()

    async def async_set_config(self, config: dict) -> None:
        enabled = bool(config.get("enabled", self.enabled))
        interval = int(config.get("interval_days", self.interval_days))
        run_time = str(config.get("run_time", self.run_time))
        if not 1 <= interval <= 30:
            raise ValueError("Frequency must be between 1 and 30 days")
        try:
            hour, minute = (int(part) for part in run_time.split(":"))
            time(hour, minute)
        except (ValueError, TypeError) as exc:
            raise ValueError("Choose a valid time") from exc
        if enabled and not self.supported:
            raise ValueError("Empty Bin support is not confirmed yet; use Empty now once to check the command")
        changed = (enabled, interval, run_time) != (self.enabled, self.interval_days, self.run_time)
        # Apply the device-side change before mutating the saved/live HA plan. If the
        # vacuum rejects this write, the schedule remains in its previous state.
        if changed and enabled:
            settings = self.coordinator.settings.get("dust") or {}
            if settings.get("auto_dust_collection"):
                await self.hass.async_add_executor_job(self.coordinator.client.set_auto_empty, False)
                await self.coordinator.async_refresh_soon()
        self.enabled, self.interval_days, self.run_time = enabled, interval, run_time
        if changed:
            self.next_run = self._next_after(dt_util.now()) if enabled else None
            self.last_error = None
        await self._save()
        self._notify()

    async def async_empty_now(self) -> None:
        if self._busy:
            raise ValueError("An Empty Bin command is already running")
        self._busy = True
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.empty_bin)
            now = dt_util.now()
            self.command_confirmed = True
            self.last_run = now.timestamp()
            self.last_error = None
            self._retry_at = 0
            if self.enabled:
                self.next_run = self._next_after(now, skip_today=True)
            await self._save()
        except Exception as exc:
            self.last_error = str(exc)
            raise
        finally:
            self._busy = False
            self._notify()

    async def _tick(self, _now) -> None:
        if not self.enabled or not self.supported or self.next_run is None or self._busy:
            return
        now = dt_util.now().timestamp()
        if now < self.next_run or now < self._retry_at:
            return
        if self.coordinator.status_code not in DOCKED_CODES:
            self._notify()
            return
        self._busy = True
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.empty_bin)
            self.last_run = now
            self.next_run = self._next_after(dt_util.now())
            self.last_error = None
            await self._save()
        except Exception as exc:
            self.last_error = str(exc)
            self._retry_at = now + 15 * 60
            _LOGGER.warning("Scheduled Empty Bin failed; will retry: %s", exc)
        finally:
            self._busy = False
            self._notify()


def _planner(hass: HomeAssistant, entity_id: str):
    ent = er.async_get(hass).async_get(entity_id)
    if ent is None or ent.platform != DOMAIN:
        return None
    coord = hass.data.get(DOMAIN, {}).get(ent.config_entry_id)
    return getattr(coord, "auto_empty_planner", None)


@callback
def async_setup_auto_empty_ws(hass: HomeAssistant) -> None:
    if hass.data.get(KEY):
        return
    hass.data[KEY] = True
    for handler in (ws_subscribe, ws_set, ws_empty):
        websocket_api.async_register_command(hass, handler)


@websocket_api.websocket_command({vol.Required("type"): "tapo_rv30/auto_empty/subscribe", vol.Required("entity_id"): str})
@callback
def ws_subscribe(hass, connection, msg):
    planner = _planner(hass, msg["entity_id"])
    if planner is None:
        connection.send_error(msg["id"], "not_found", "Auto-empty planner unavailable")
        return
    @callback
    def forward():
        connection.send_message(websocket_api.event_message(msg["id"], planner.view))
    connection.subscriptions[msg["id"]] = planner.add_listener(forward)
    connection.send_result(msg["id"])
    forward()


@websocket_api.websocket_command({vol.Required("type"): "tapo_rv30/auto_empty/set", vol.Required("entity_id"): str,
                                  vol.Required("config"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set(hass, connection, msg):
    planner = _planner(hass, msg["entity_id"])
    if planner is None:
        connection.send_error(msg["id"], "not_found", "Auto-empty planner unavailable")
        return
    try:
        await planner.async_set_config(msg["config"])
    except (ValueError, TypeError) as exc:
        connection.send_error(msg["id"], "invalid", str(exc))
        return
    connection.send_result(msg["id"], planner.view)


@websocket_api.websocket_command({vol.Required("type"): "tapo_rv30/auto_empty/empty", vol.Required("entity_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_empty(hass, connection, msg):
    planner = _planner(hass, msg["entity_id"])
    if planner is None:
        connection.send_error(msg["id"], "not_found", "Auto-empty planner unavailable")
        return
    try:
        await planner.async_empty_now()
    except Exception as exc:
        connection.send_error(msg["id"], "failed", str(exc))
        return
    connection.send_result(msg["id"], planner.view)
