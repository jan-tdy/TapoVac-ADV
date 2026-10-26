"""Smart cleaning planner: the Home Assistant side.

Ported from upstream epg-pers/tapo-rv30-ha v0.20.0 (planner.py) and extended
for this fork:

- room occupancy that works without motion sensors: besides motion /
  occupancy binary sensors in the room's areas, a person whose Home Assistant
  state is the area's name (area presence) counts as the room being in use,
  and any entity can be added per room with its own "busy" states.
- an away condition that can watch any entity (an input_boolean "someone is
  home" switch, a device tracker, a group) in addition to the upstream
  person-entity list.
- a configurable run policy: one run per window (upstream) or repeat while
  rooms are due, with a minimum gap between runs.
- optional notifications: a persistent notification, writing into the user's
  own input_text helper or text entity, and/or calling a notify service.

Each minute, and whenever a watched person, sensor or the robot changes,
this gathers the house and robot state into a planlogic.Snapshot and asks
planlogic.decide what to do. It then starts a room clean (or, in preview,
only logs what it would have done), docks the robot when someone comes home
mid-run, keeps a short decision log, and pushes its view to the panel and
the planner entities. Config and log are stored per robot.

Rooms come from the robot's current map; which Home Assistant areas they
belong to comes from the vacuum entity's own "map rooms to areas" setting,
the same one vacuum.clean_area uses, so nothing is mapped twice.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CLEANING_CODES, DOCKED_CODES, DOMAIN
from .mapdata import b64name
from .planlogic import (
    TARGET_CHOICES,
    Decision,
    PlannerError,
    RoomState,
    Snapshot,
    busy_state,
    decide,
    in_window,
    merged_config,
    merged_notify,
    next_window_start,
    room_score,
    room_status,
    room_target,
    sensors_in_use,
    simulate_windows,
    validate_changes,
    window_key,
)

_LOGGER = logging.getLogger(__name__)

EVENT_PLANNER = f"{DOMAIN}_planner"
OCCUPANCY_CLASSES = {"motion", "occupancy", "presence"}
LOG_SIZE = 40
RETRY_AFTER_FAILURE = 15 * 60
BLOCKED_NOTIFY_GAP = 30 * 60     # with notify when=start_and_blocked: at most this often


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s.replace("&", " and ")).strip()


class TapoPlanner:
    def __init__(self, hass: HomeAssistant, coordinator, entry) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entry = entry
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.planner")
        self.config: dict = merged_config(None)
        self.log: list[dict] = []
        self.skip_today: str | None = None
        self.room_skips: dict[str, str] = {}
        self.ran_window: str | None = None
        self.last_run_ts: float | None = None
        self.preview_names: list[str] = []
        self.preview_window: str | None = None
        self.last_preview_ts: float | None = None
        self.decision: Decision | None = None
        self.view: dict = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._unsub_states: Callable[[], None] | None = None
        self._watched: tuple[str, ...] = ()
        self._run: dict | None = None
        self._last_wait: str | None = None
        self._last_blocked_notify = 0.0
        self._retry_at = 0.0
        self._evaluating = False
        self._again = False

    # ---- lifecycle -------------------------------------------------------------------
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.config = merged_config(data.get("config"))
        self.log = list(data.get("log") or [])[:LOG_SIZE]
        self.skip_today = data.get("skip_today")
        self.room_skips = dict(data.get("room_skips") or {})
        self.ran_window = data.get("ran_window")
        self.last_run_ts = data.get("last_run_ts")
        self.preview_names = list(data.get("preview_names") or [])
        self.preview_window = data.get("preview_window")
        self.last_preview_ts = data.get("last_preview_ts")

    def _save(self) -> None:
        self._store.async_delay_save(lambda: {
            "config": self.config, "log": self.log, "skip_today": self.skip_today,
            "room_skips": self.room_skips, "ran_window": self.ran_window,
            "last_run_ts": self.last_run_ts, "preview_names": self.preview_names,
            "preview_window": self.preview_window, "last_preview_ts": self.last_preview_ts}, 2)

    @callback
    def async_start(self) -> None:
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, timedelta(seconds=60)))
        self._unsubs.append(self.coordinator.async_add_listener(self._on_coordinator))
        self._rewatch()
        self._schedule("start")

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None

    @callback
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)

        def remove() -> None:
            if cb in self._listeners:
                self._listeners.remove(cb)
        return remove

    @callback
    def _notify_listeners(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # a dead websocket must not stop the others
                _LOGGER.debug("Planner listener failed", exc_info=True)

    @callback
    def _on_tick(self, _now) -> None:
        self._schedule("tick")

    @callback
    def _on_coordinator(self) -> None:
        self._schedule("robot")

    @callback
    def _on_state(self, _event: Event) -> None:
        self._schedule("house")

    @callback
    def _schedule(self, reason: str) -> None:
        if self._evaluating:
            self._again = True
            return
        self.hass.async_create_task(self.async_evaluate(reason))

    # ---- the house ---------------------------------------------------------------------
    @property
    def vacuum_entity_id(self) -> str | None:
        return er.async_get(self.hass).async_get_entity_id("vacuum", DOMAIN, f"{self.entry.entry_id}_vacuum")

    def area_mapping(self) -> dict[str, list[str]]:
        """The vacuum entity's own "map rooms to areas": area id -> segment ids."""
        eid = self.vacuum_entity_id
        entry = er.async_get(self.hass).async_get(eid) if eid else None
        opts = (entry.options.get("vacuum") or {}) if entry else {}
        return dict(opts.get("area_mapping") or {})

    def room_areas(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for area_id, segs in self.area_mapping().items():
            for seg in segs or []:
                out.setdefault(seg, []).append(area_id)
        return out

    def occupancy_sensors(self) -> list[dict]:
        """Every motion / occupancy / presence binary sensor, with its area."""
        ents, devs = er.async_get(self.hass), dr.async_get(self.hass)
        areas = ar.async_get(self.hass)
        out = []
        for st in self.hass.states.async_all("binary_sensor"):
            if st.attributes.get("device_class") not in OCCUPANCY_CLASSES:
                continue
            entry = ents.async_get(st.entity_id)
            area_id = entry.area_id if entry else None
            if not area_id and entry and entry.device_id:
                dev = devs.async_get(entry.device_id)
                area_id = dev.area_id if dev else None
            area = areas.async_get_area(area_id) if area_id else None
            out.append({"entity_id": st.entity_id, "name": st.name, "area_id": area_id,
                        "area": area.name if area else None})
        return sorted(out, key=lambda s: ((s["area"] or "~"), s["name"]))

    def _sensors_by_area(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for s in self.occupancy_sensors():
            if s["area_id"]:
                out.setdefault(s["area_id"], []).append(s["entity_id"])
        return out

    def rooms(self) -> list[tuple[str, str]]:
        """(key, name) for the current map's rooms; key = "map_id:room_id" like the segments."""
        map_id = self.coordinator.map_id
        if map_id is None:
            return []
        return [(f"{map_id}:{r['id']}", b64name(r.get("name", "")) or f"Room {r['id']}")
                for r in self.coordinator.rooms]

    def _room_cfg(self, key: str) -> dict:
        return dict(self.config["rooms"].get(key) or {})

    def room_sensor_ids(self, key: str, room_areas: dict, by_area: dict[str, list[str]]) -> tuple[list[str], set[str]]:
        """(entity ids the room listens to, the ones that came from its areas)."""
        rc = self._room_cfg(key)
        auto = {sid for area_id in room_areas.get(key, []) for sid in by_area.get(area_id, [])}
        if rc.get("ignore_occupancy"):
            return [], auto
        chosen = (auto - set(rc.get("remove_sensors") or [])) | set(rc.get("add_sensors") or [])
        return sorted(chosen), auto

    def people(self) -> list[dict]:
        chosen = self.config.get("people")
        out = []
        for st in self.hass.states.async_all("person"):
            out.append({"entity_id": st.entity_id, "name": st.name, "home": st.state == "home",
                        "included": chosen is None or st.entity_id in chosen})
        return sorted(out, key=lambda p: p["name"])

    def people_in_area(self, area_names: list[str]) -> list[tuple[str, str]]:
        """(entity_id, name) of person entities whose state is one of the area names —
        Home Assistant's area presence (a person standing in the kitchen has the
        kitchen's name as its state). Works without any motion sensor."""
        wanted = {_norm(a) for a in area_names if a}
        out = []
        if not wanted:
            return out
        for st in self.hass.states.async_all("person"):
            if _norm(st.state) in wanted:
                out.append((st.entity_id, st.name))
        return out

    def house_occupied(self) -> list[str]:
        """Names of who counts as home right now (feeds decide's require_away)."""
        if self.config.get("away_source") == "entity":
            entity_id = self.config.get("away_entity")
            if not entity_id:
                return []
            st = self.hass.states.get(entity_id)
            if st is None or st.state in ("unavailable", "unknown"):
                return []
            # the configured home states decide here — even for a person or
            # tracker: busy_state()'s "a person is busy unless home" rule is
            # for room occupancy, not for the away condition
            home_states = list(self.config.get("away_home_states") or ["home", "on"])
            if st.state in home_states:
                return [st.name or entity_id]
            return []
        return [p["name"] for p in self.people() if p["included"] and p["home"]]

    @callback
    def _rewatch(self) -> None:
        room_areas, by_area = self.room_areas(), self._sensors_by_area()
        ids = {p["entity_id"] for p in self.people()}
        for key, _ in self.rooms():
            ids.update(self.room_sensor_ids(key, room_areas, by_area)[0])
        # people standing in a room's area are only found by state, so watch every person
        if self.config.get("occupancy_sources", {}).get("area_people", True):
            ids.update(st.entity_id for st in self.hass.states.async_all("person"))
        if self.config.get("away_source") == "entity" and self.config.get("away_entity"):
            ids.add(self.config["away_entity"])
        watched = tuple(sorted(ids))
        if watched == self._watched:
            return
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None
        self._watched = watched
        if watched:
            self._unsub_states = async_track_state_change_event(self.hass, list(watched), self._on_state)

    # ---- snapshot and decision ---------------------------------------------------------
    def _room_in_use(self, key: str, room_areas: dict, by_area: dict[str, list[str]],
                     now_ts: float) -> list[str]:
        """Names of whatever makes this room in use right now."""
        rc = self._room_cfg(key)
        if rc.get("ignore_occupancy"):
            return []
        sources = self.config.get("occupancy_sources") or {}
        readings: list[tuple[str, bool, float | None]] = []
        if sources.get("area_sensors", True):
            # only the automatic area sensors here — a manually added entity
            # belongs to the "manual" source below, so its toggle stays effective
            sensor_ids, auto = self.room_sensor_ids(key, room_areas, by_area)
            for sid in (s for s in sensor_ids if s in auto):
                st = self.hass.states.get(sid)
                if st is not None and st.state not in ("unavailable", "unknown"):
                    readings.append((st.name, st.state == "on", st.last_changed.timestamp()))
        if sources.get("area_people", True):
            area_names = [a.name for a in ar.async_get(self.hass).async_list_areas()
                          if a.id in room_areas.get(key, [])]
            for _eid, name in self.people_in_area(area_names):
                readings.append((name, True, now_ts))
        if sources.get("manual", True) and not rc.get("ignore_occupancy"):
            for sid in rc.get("add_sensors") or []:
                st = self.hass.states.get(sid)
                if st is not None and st.state not in ("unavailable", "unknown"):
                    # a person/tracker is busy unless home; anything else when on
                    readings.append((st.name, busy_state(sid, st.state, ["on"]),
                                     st.last_changed.timestamp()))
        return sensors_in_use(readings, now_ts, int(self.config["clear_minutes"]))

    def snapshot(self) -> Snapshot:
        now = dt_util.now()
        robot_now = None
        clock = self.coordinator.settings.get("clock") or {}
        try:
            timestamp = float(clock.get("time"))
            offset = float(clock.get("time_diff") or 0)
            robot_now = dt_util.as_local(dt_util.utc_from_timestamp(timestamp + offset * 60))
            now = robot_now
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
        now_ts = now.timestamp()
        today = now.strftime("%Y-%m-%d")
        data = self.coordinator.data or {}
        code = data.get("status_code")
        room_areas, by_area = self.room_areas(), self._sensors_by_area()
        rooms = []
        for key, name in self.rooms():
            in_use = self._room_in_use(key, room_areas, by_area, now_ts) if self.config["skip_in_use"] else []
            last = (self.coordinator.rooms_last_cleaned.get(key) or {}).get("last_cleaned")
            rooms.append(RoomState(key, name, last, room_target(self.config, key), in_use,
                                   self.room_skips.get(key) == today))
        ran = self.ran_window
        if self.config.get("runs_per_window") == "repeat":
            gap = int(self.config.get("min_run_gap_minutes", 120)) * 60
            ran = None if (self.last_run_ts is None or now_ts - self.last_run_ts >= gap) else window_key(now)
        return Snapshot(
            now=now, robot_docked=code in DOCKED_CODES, robot_busy=self.coordinator.busy,
            robot_error=(data.get("error_codes") or [0])[0] not in (0, None),
            battery=data.get("battery"), dnd=self.coordinator.settings.get("dnd"),
            people_home=self.house_occupied() if self.config["require_away"] else [],
            schedules=list(self.coordinator.schedules or []),
            skip_today=self.skip_today == today, ran_window=ran, rooms=rooms, robot_now=robot_now)

    async def async_evaluate(self, reason: str = "") -> None:
        if self._evaluating:
            self._again = True
            return
        self._evaluating = True
        try:
            while True:
                self._again = False
                await self._evaluate_once(reason)
                if not self._again:
                    break
        finally:
            self._evaluating = False

    async def _evaluate_once(self, reason: str) -> None:
        if self.coordinator.data is None or self.coordinator.map_id is None:
            return
        snap = self.snapshot()
        await self._follow_run(snap)
        d = decide(snap, self.config)
        started = False
        if d.action == "clean" and time.time() >= self._retry_at:
            if self.config.get("preview"):
                # Note a preview once per window (or repeat gap) so the log stays
                # quiet — but never consume the run for it: turning preview off
                # mid-window must let the real clean start right away. ran_window
                # and last_run_ts are only ever set by a real start (_start).
                fresh = False
                if self.config.get("runs_per_window") == "repeat":
                    gap_s = int(self.config.get("min_run_gap_minutes", 120)) * 60
                    fresh = self.last_preview_ts is None or time.time() - self.last_preview_ts >= gap_s
                    if fresh:
                        self.last_preview_ts = time.time()
                else:
                    key = window_key(snap.robot_now or snap.now)
                    fresh = self.preview_window != key
                    if fresh:
                        self.preview_window = key
                if fresh:
                    self.preview_names = list(d.names)
                    self._log("preview", f"Preview: would have cleaned {self._and(d.names)}. " + "; ".join(d.chips))
                    self._fire("preview", d)
                    self._save()
            else:
                started = await self._start(snap, d.rooms, d.names, d.chips, by="planner")
            d = decide(self.snapshot(), self.config)
        elif d.action == "wait" and d.rooms and d.waiting_for not in ("window", "ran", "skipped") \
                and d.status != self._last_wait:
            self._log("wait", d.status)
            self._save()
            self._maybe_notify_blocked(d)
        if d.action == "clean" and not started and not self.config.get("preview"):
            d = self._not_started(d)
        if d.action == "wait" and d.waiting_for == "ran" and self.config.get("runs_per_window") == "repeat":
            gap = int(self.config.get("min_run_gap_minutes", 120))
            left = max(0, gap - int((time.time() - (self.last_run_ts or 0)) // 60))
            d = Decision(d.action, f"Waiting {left} min between runs", d.rooms, d.names, d.chips, d.waiting_for)
        self._last_wait = d.status if d.action == "wait" else None
        self.decision = d
        self.view = self._build_view(snap, d)
        self._notify_listeners()

    def _not_started(self, d: Decision) -> Decision:
        """Show a retry wait when due rooms could not actually be started."""
        at = dt_util.as_local(dt_util.utc_from_timestamp(
            self._retry_at if time.time() < self._retry_at else time.time() + 60))
        return Decision("wait", f"Could not start; trying again at {at.strftime('%H:%M')}",
                        d.rooms, d.names, d.chips, "retry")

    async def _start(self, snap: Snapshot, keys: list[str], names: list[str], chips: list[str], by: str) -> bool:
        map_id = self.coordinator.map_id
        room_ids = [int(k.split(":", 1)[1]) for k in keys]
        try:
            await self.hass.async_add_executor_job(self.coordinator.client.clean_rooms, room_ids, map_id)
        except Exception as exc:
            self._retry_at = time.time() + RETRY_AFTER_FAILURE
            self._log("error", f"Could not start cleaning {self._and(names)}: {exc}. Trying again in 15 minutes.")
            self._save()
            return False
        self.ran_window = window_key(snap.robot_now or snap.now)
        self.last_run_ts = time.time()
        self._run = {"names": names, "started": time.time(), "dock_after": None, "docked": False}
        why = (" " + "; ".join(chips) + ".") if chips else ""
        who = "You started" if by == "user" else "Started"
        self._log("start", f"{who} cleaning {self._and(names)}.{why}")
        self._fire("start", None, names=names, by=by)
        note = merged_notify(self.config)
        if note.get("when", "start") in ("start", "start_and_blocked"):
            self._notify(f"{self.coordinator.device_name}: {who.lower()} cleaning {self._and(names)}.")
        self._save()
        await self.coordinator.async_refresh_soon()
        return True

    def _maybe_notify_blocked(self, d: Decision) -> None:
        """With notify when=start_and_blocked: tell the user when a due set keeps
        waiting for something other than the window itself, at most once half-hourly."""
        note = merged_notify(self.config)
        if note.get("when") != "start_and_blocked":
            return
        if time.time() - self._last_blocked_notify < BLOCKED_NOTIFY_GAP:
            return
        self._last_blocked_notify = time.time()
        self._notify(f"{self.coordinator.device_name}: {d.status} "
                     f"({', '.join(d.names)} due).")

    def _notify(self, text: str) -> None:
        """Fan the message out to the configured targets (any combination)."""
        note = merged_notify(self.config)
        try:
            if note.get("persistent"):
                from homeassistant.components import persistent_notification
                persistent_notification.async_create(self.hass, text, title="Tapo cleaning planner")
            if note.get("input_text"):
                self.hass.async_create_task(self.hass.services.async_call(
                    "input_text", "set_value",
                    {"entity_id": note["input_text"], "value": text[:255]}, blocking=False))
            if note.get("text_entity"):
                st = self.hass.states.get(note["text_entity"])
                limit = st.attributes.get("max", 100) if st else 100
                try:
                    limit = max(1, int(limit))
                except (TypeError, ValueError):
                    limit = 100
                self.hass.async_create_task(self.hass.services.async_call(
                    "text", "set_value",
                    {"entity_id": note["text_entity"], "value": text[:limit]}, blocking=False))
            if note.get("notify_service"):
                domain, service = note["notify_service"].split(".", 1)
                self.hass.async_create_task(
                    self.hass.services.async_call(domain, service, {"message": text}, blocking=False))
        except Exception:  # a broken notification target must never break a clean
            _LOGGER.debug("Planner notification failed", exc_info=True)

    async def _follow_run(self, snap: Snapshot) -> None:
        """While a planner run is going: notice the end, and dock if someone comes home."""
        run = self._run
        if not run:
            return
        code = (self.coordinator.data or {}).get("status_code")
        if code in DOCKED_CODES and time.time() - run["started"] > 120:
            if not run["docked"]:
                self._log("done", f"Finished cleaning {self._and(run['names'])}.")
                self._save()
            self._run = None
            return
        if run["docked"] or self.config.get("on_return") != "finish_room" or not self.config.get("require_away"):
            return
        if code not in CLEANING_CODES or not snap.people_home:
            return
        room = self.coordinator.current_room or ""
        if run["dock_after"] is None:
            run["dock_after"] = room
            self._log("return", f"{self._and(snap.people_home)} came home: finishing "
                      f"{('the ' + room) if room else 'this room'}, then docking.")
            self._save()
        elif room and room != run["dock_after"]:
            try:
                await self.hass.async_add_executor_job(self.coordinator.client.dock)
            except Exception as exc:
                self._log("error", f"Could not send the robot home: {exc}")
            else:
                run["docked"] = True
                self._log("docked", "Sent home: someone is home.")
            self._save()

    # ---- actions ---------------------------------------------------------------------
    async def async_clean_now(self) -> None:
        snap = self.snapshot()
        if snap.robot_error:
            raise PlannerError("The robot reports a problem")
        if snap.robot_busy or not snap.robot_docked:
            raise PlannerError("The robot is busy")
        now_ts = snap.now.timestamp()
        due = sorted(((room_score(r.last_cleaned, r.target_days, now_ts) or 0, r) for r in snap.rooms
                      if not r.skipped_today and (room_score(r.last_cleaned, r.target_days, now_ts) or 0) >= 1),
                     key=lambda t: -t[0])
        if not due:
            raise PlannerError("Nothing is due")
        await self._start(snap, [r.key for _, r in due], [r.name for _, r in due], [], by="user")
        await self.async_evaluate("clean_now")

    async def async_skip_today(self, on: bool) -> None:
        self.skip_today = dt_util.now().strftime("%Y-%m-%d") if on else None
        self._log("skip", "Skipped for today." if on else "Back on for today.")
        self._save()
        await self.async_evaluate("skip")

    async def async_skip_room_today(self, key: str, on: bool) -> None:
        names = dict(self.rooms())
        if key not in names:
            raise PlannerError(f"No room {key} on the current map")
        if on:
            self.room_skips[key] = dt_util.now().strftime("%Y-%m-%d")
        else:
            self.room_skips.pop(key, None)
        self._log("skip", f"{'Leaving out' if on else 'Including'} {names[key]} today.")
        self._save()
        await self.async_evaluate("skip_room")

    async def async_set_config(self, changes: dict) -> None:
        self.config = merged_config({**self.config, **validate_changes(changes, self.config)})
        if "enabled" in changes:
            self._log("config", "Planner turned on." if self.config["enabled"] else "Planner turned off.")
        if "preview" in changes:
            self._log("config", "Preview mode on: nothing will start." if self.config["preview"]
                      else "Preview mode off: the planner will start the robot.")
        self._save()
        self._rewatch()
        await self.async_evaluate("config")

    async def async_match_areas(self) -> list[str]:
        """Map the current map's unmapped rooms to Home Assistant areas with the same name,
        in the vacuum entity's own mapping. Returns the room names matched."""
        eid = self.vacuum_entity_id
        if not eid:
            raise PlannerError("The vacuum entity is not registered")
        ents = er.async_get(self.hass)
        entry = ents.async_get(eid)
        opts = dict((entry.options.get("vacuum") or {}) if entry else {})
        mapping = {a: list(s) for a, s in (opts.get("area_mapping") or {}).items()}
        mapped = {seg for segs in mapping.values() for seg in segs}
        by_name = {_norm(a.name): a.id for a in ar.async_get(self.hass).async_list_areas()}
        matched = []
        for key, name in self.rooms():
            area_id = by_name.get(_norm(name))
            if key in mapped or not area_id:
                continue
            mapping.setdefault(area_id, []).append(key)
            matched.append(name)
        if matched:
            group = self.coordinator.map_name or None
            seen = [{"id": k, "name": n, "group": group} for k, n in self.rooms()]
            others = [s for s in (opts.get("last_seen_segments") or []) if not str(s.get("id", "")).startswith(
                f"{self.coordinator.map_id}:")]
            ents.async_update_entity_options(eid, "vacuum", {**opts, "area_mapping": mapping,
                                                            "last_seen_segments": others + seen})
            self._log("config", f"Matched to areas by name: {', '.join(matched)}.")
            self._save()
            self._rewatch()
            await self.async_evaluate("match")
        return matched

    # ---- helpers ---------------------------------------------------------------------
    @staticmethod
    def _and(names: list[str]) -> str:
        names = list(names)
        if not names:
            return "nothing"
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    def _log(self, kind: str, text: str) -> None:
        self.log.insert(0, {"ts": time.time(), "kind": kind, "text": text})
        del self.log[LOG_SIZE:]

    def _fire(self, kind: str, d: Decision | None, **extra: Any) -> None:
        self.hass.bus.async_fire(EVENT_PLANNER, {
            **self.coordinator._event_base(),
            "kind": kind, "rooms": list(d.names) if d else extra.get("names", []), **extra})

    def _build_view(self, snap: Snapshot, d: Decision) -> dict:
        now_ts = snap.now.timestamp()
        room_areas, by_area = self.room_areas(), self._sensors_by_area()
        area_names = {a.id: a.name for a in ar.async_get(self.hass).async_list_areas()}
        names = {s["entity_id"]: s["name"] for s in self.occupancy_sensors()}
        rooms = []
        for r in snap.rooms:
            sensor_ids, auto = self.room_sensor_ids(r.key, room_areas, by_area)
            rc = self._room_cfg(r.key)
            score = room_score(r.last_cleaned, r.target_days, now_ts)
            sensors = [{"entity_id": s, "name": names.get(s, s), "source": "area"} for s in sensor_ids if s in auto]
            if not rc.get("ignore_occupancy"):
                for sid in rc.get("add_sensors") or []:
                    st = self.hass.states.get(sid)
                    sensors.append({"entity_id": sid, "name": st.name if st else sid, "source": "manual",
                                    "busy_now": bool(st and st.state not in ("unavailable", "unknown")
                                                     and busy_state(sid, st.state, ["on"]))})
            rooms.append({
                "key": r.key, "name": r.name, "last_cleaned": r.last_cleaned, "target_days": r.target_days,
                "status": room_status(r.last_cleaned, r.target_days, now_ts),
                "score": round(score, 2) if score is not None else None,
                "areas": [{"id": a, "name": area_names.get(a, a)} for a in room_areas.get(r.key, [])],
                "sensors": sensors,
                "removed": sorted(set(rc.get("remove_sensors") or []) & auto),
                "in_use_by": r.in_use_by, "skipped_today": r.skipped_today,
                "ignore_occupancy": bool(rc.get("ignore_occupancy")),
            })
        status = d.status
        if self.config.get("preview") and self.preview_names and d.action == "clean":
            status = f"Preview: would have cleaned {self._and(self.preview_names)} today"
        opens = next_window_start(snap.now, self.config)
        away_entity = self.config.get("away_entity")
        away_st = self.hass.states.get(away_entity) if away_entity else None
        return {
            "entity_id": self.vacuum_entity_id, "device": self.coordinator.device_name,
            "status": status, "action": d.action, "waiting_for": d.waiting_for,
            "due": d.names, "chips": d.chips, "in_window": in_window(snap.now, self.config),
            "next_window": opens.isoformat(), "now": snap.now.isoformat(),
            "timeline": simulate_windows(snap, self.config),
            "skip_today": snap.skip_today, "running": bool(self._run),
            "rooms": rooms, "people": self.people(), "sensors": self.occupancy_sensors(),
            "unmapped": [r["name"] for r in rooms if not r["areas"]],
            "target_choices": list(TARGET_CHOICES), "config": self.config, "log": self.log[:20],
            "battery": snap.battery,
            "away": {"source": self.config.get("away_source"), "entity": away_entity,
                     "entity_state": away_st.state if away_st else None,
                     "home": bool(snap.people_home), "who": list(snap.people_home)},
            "last_run_ts": self.last_run_ts,
        }
