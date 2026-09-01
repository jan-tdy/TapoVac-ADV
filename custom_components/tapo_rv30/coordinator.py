"""DataUpdateCoordinator for Tapo RV30."""
from __future__ import annotations

import base64
import logging
import unicodedata
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from PIL import Image, ImageDraw, ImageFont

from .const import (
    DOMAIN,
    FAST_INTERVAL,
    MAP_INTERVAL,
    MAP_INTERVAL_ACTIVE,
    ROOM_PALETTE,
    VACUUM_STATES,
    WALL_COLOR,
    UNKNOWN_COLOR,
    FLOOR_COLOR,
)
from .tpap import TapoVacuumClient

_LOGGER = logging.getLogger(__name__)

MAP_SCALE = 4   # px per vacuum grid cell → ~700×700 output image


def _lz4_block_decompress(data: bytes, uncompressed_size: int) -> bytes:
    """Pure-Python LZ4 block decompressor — no C extension needed."""
    out = bytearray(uncompressed_size)
    src = 0
    dst = 0
    n = len(data)
    while src < n:
        token = data[src]; src += 1
        # Literal run
        lit_len = token >> 4
        if lit_len == 15:
            while src < n:
                extra = data[src]; src += 1
                lit_len += extra
                if extra != 255:
                    break
        out[dst:dst + lit_len] = data[src:src + lit_len]
        src += lit_len
        dst += lit_len
        if src >= n:
            break
        # Match copy
        offset = data[src] | (data[src + 1] << 8); src += 2
        match_len = (token & 0xF) + 4
        if match_len == 19:  # 4 + 15
            while src < n:
                extra = data[src]; src += 1
                match_len += extra
                if extra != 255:
                    break
        match_pos = dst - offset
        for i in range(match_len):
            out[dst + i] = out[match_pos + i]
        dst += match_len
    return bytes(out)
FONT_SIZE  = 14


def _b64name(s: str) -> str:
    try:
        return base64.b64decode(s).decode(errors="replace").strip()
    except Exception:
        return s


def _fold(s: str) -> str:
    """Lowercase and strip diacritics (á/č/ľ/ň/š/ť/ž/ô/ä/ú → a/c/l/n/s/t/z/o/a/u).

    Lets room/map names set with accented characters in the Tapo app (e.g.
    Slovak "Kúpeľňa") be matched by typing a plain-ASCII pattern such as
    "kupelna" or "pel" — handy since some clients (e.g. Home Assistant's
    Developer Tools → Actions text fields) make accented characters awkward
    to type.
    """
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


# Confirmed against a real device: a test schedule set for Mon/Wed/Fri came
# back with week_day=42, and 2(Mon)+8(Wed)+32(Fri)=42 exactly under this
# Sun=1..Sat=64 bitmask convention — not a guess, an exact numeric match
# (credit: github.com/peggleg/tapo-rv30, which discovered get_schedule_rules).
_WEEKDAY_BITS = [
    (1,  "Sun"), (2,  "Mon"), (4,  "Tue"), (8,  "Wed"),
    (16, "Thu"), (32, "Fri"), (64, "Sat"),
]


def _decode_weekdays(mask: int) -> list[str]:
    return [name for bit, name in _WEEKDAY_BITS if mask & bit]


def _decode_schedule(rule: dict, room_names: dict[int, str]) -> dict:
    """Turn one raw schedule rule (from get_schedule_rules) into a
    human-readable summary — time, repeat days, rooms, and clean settings,
    exactly as configured for that schedule in the Tapo app."""
    attr = rule.get("clean_attr", {})
    room_ids = attr.get("room_list", [])
    custom_rule_id = attr.get("custom_rule_id")
    s_min = rule.get("s_min", 0)
    return {
        "id":              rule.get("id"),
        "enabled":         rule.get("enable", False),
        "time":            f"{s_min // 60:02d}:{s_min % 60:02d}",
        "days":            _decode_weekdays(rule.get("week_day", 0)),
        "repeat":          rule.get("mode") == "repeat",
        "rooms":           [room_names.get(rid, f"Room {rid}") for rid in room_ids],
        "room_ids":        room_ids,
        "clean_order":     attr.get("clean_order", False),
        "suction":         attr.get("suction"),
        "water_level":     attr.get("cistern"),
        "clean_passes":    attr.get("clean_number"),
        # clean_mode 5 + custom_rule_id shows up on schedules built from a
        # named "cleaning preset" in the Tapo app, instead of an inline
        # room_list (clean_mode 3) — confirmed against a real device's raw
        # schedule data. There's no known call to resolve a custom_rule_id
        # back to actual room names, so "preset" is as specific as this can
        # currently get; see run_schedule()/clean_custom_rule() in tpap.py.
        "clean_mode":      attr.get("clean_mode"),
        "custom_rule_id":  custom_rule_id,
        "is_preset":       custom_rule_id is not None,
        "map_id":          attr.get("map_id"),
        # Undecoded passthrough, for anything not surfaced above yet.
        "raw":             rule,
    }


def _room_at_vac(map_data: dict) -> dict | None:
    """Return the room (from area_list) the vacuum currently occupies,
    inferred locally from vac_coor against the same room-id pixel buffer
    getMapData already provides — no extra device call needed.

    None if vac_coor is missing/out of bounds, or the vacuum's position
    lands on a non-room pixel (wall, unexplored, or scanned floor with no
    room assigned — e.g. a hallway, or a dock not placed inside a room).
    """
    vac = map_data.get("vac_coor")
    if not vac:
        return None
    width, height, pix_len = map_data["width"], map_data["height"], map_data["pix_len"]
    gx, gy = int(vac[0]), int(vac[1])
    if not (0 <= gx < width and 0 <= gy < height):
        return None

    raw    = base64.b64decode(map_data["map_data"])
    pixels = _lz4_block_decompress(raw, uncompressed_size=pix_len)
    room_id = pixels[gy * width + gx]

    return next(
        (a for a in map_data.get("area_list", [])
         if a.get("type") == "room" and a.get("id") == room_id),
        None,
    )


def _render_map_image(map_data: dict) -> bytes:
    """Decode LZ4 pixel data and produce a JPEG image as bytes."""
    width   = map_data["width"]
    height  = map_data["height"]
    pix_len = map_data["pix_len"]

    raw     = base64.b64decode(map_data["map_data"])
    pixels  = _lz4_block_decompress(raw, uncompressed_size=pix_len)

    rooms = [a for a in map_data.get("area_list", []) if a.get("type") == "room"]
    sorted_ids  = sorted(r["id"] for r in rooms)
    room_colors = {rid: ROOM_PALETTE[i % len(ROOM_PALETTE)]
                   for i, rid in enumerate(sorted_ids)}

    # Build colour lookup table (0-255)
    lut: list[tuple[int, int, int]] = [UNKNOWN_COLOR] * 256
    lut[0]   = WALL_COLOR
    lut[127] = UNKNOWN_COLOR
    lut[255] = FLOOR_COLOR
    for rid, color in room_colors.items():
        if 0 <= rid <= 255:
            lut[rid] = color

    # Map each pixel byte to its RGB colour via three vectorized C-level
    # byte.translate() lookups (one per channel) instead of a per-pixel
    # Python draw call — orders of magnitude fewer Python-level ops on a
    # large map. bytes.translate() maps each byte through a 256-entry table.
    r_table = bytes(c[0] for c in lut)
    g_table = bytes(c[1] for c in lut)
    b_table = bytes(c[2] for c in lut)
    low_res = Image.merge("RGB", (
        Image.frombytes("L", (width, height), pixels.translate(r_table)),
        Image.frombytes("L", (width, height), pixels.translate(g_table)),
        Image.frombytes("L", (width, height), pixels.translate(b_table)),
    ))
    # Pixel row 0 is the bottom of real space; flip so screen row 0 is the top.
    low_res = low_res.transpose(Image.FLIP_TOP_BOTTOM)
    img  = low_res.resize((width * MAP_SCALE, height * MAP_SCALE), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(img)

    # Room name labels centred in each room
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                  FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    # Centroid of every room in one pass over the pixel buffer, instead of
    # re-scanning the whole buffer once per room.
    room_ids_set = set(room_colors)
    sum_x: dict[int, int] = {}
    sum_y: dict[int, int] = {}
    count: dict[int, int] = {}
    for row in range(height):
        row_offset = row * width
        for col in range(width):
            pv = pixels[row_offset + col]
            if pv in room_ids_set:
                sum_x[pv] = sum_x.get(pv, 0) + col
                sum_y[pv] = sum_y.get(pv, 0) + row
                count[pv] = count.get(pv, 0) + 1

    for room in rooms:
        rid = room["id"]
        if rid not in room_colors or not count.get(rid):
            continue
        name = _b64name(room.get("name", ""))
        cx = int(sum_x[rid] / count[rid]) * MAP_SCALE + MAP_SCALE // 2
        cy = int((height - 1 - (sum_y[rid] / count[rid]))) * MAP_SCALE + MAP_SCALE // 2

        # Shadow + white label
        draw.text((cx + 1, cy + 1), name, fill=(0, 0, 0, 180), font=font, anchor="mm")
        draw.text((cx, cy),         name, fill=(255, 255, 255), font=font, anchor="mm")

    # Charger and vacuum markers
    charge = map_data.get("charge_coor")
    vac    = map_data.get("vac_coor")

    def _dot(gx, gy, color, radius=6):
        sx = gx * MAP_SCALE + MAP_SCALE // 2
        sy = (height - 1 - gy) * MAP_SCALE + MAP_SCALE // 2
        draw.ellipse([sx - radius, sy - radius, sx + radius, sy + radius],
                     fill=color, outline=(255, 255, 255), width=2)

    if charge:
        _dot(charge[0], charge[1], (255, 200, 0))   # amber = dock
    if vac:
        _dot(vac[0], vac[1], (0, 180, 255))          # cyan = vacuum

    import io
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


class TapoCoordinator(DataUpdateCoordinator):
    """Polls Jarvis for status + periodically re-renders map."""

    def __init__(self, hass: HomeAssistant, client: TapoVacuumClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=FAST_INTERVAL),
        )
        self.client          = client
        self._map_tick       = 0      # counts update cycles; refresh map every N
        self._map_cycles_idle   = MAP_INTERVAL // FAST_INTERVAL
        self._map_cycles_active = MAP_INTERVAL_ACTIVE // FAST_INTERVAL
        self.map_image_bytes: bytes | None = None
        self.rooms:  list[dict] = []   # current rooms (area_list, type==room)
        self.map_id: int | None = None # current map_id
        self.schedules: list[dict] = []  # decoded get_schedule_rules
        self.device_name:  str = "Tapo RV30"
        self._name_fetched = False
        self.current_room: str | None = None  # room name at last map refresh
        self.dock_features: set[str] = set()  # probed dock actions — see tpap.DOCK_FEATURES
        self._dock_features_fetched = False

    async def _async_update_data(self) -> dict[str, Any]:
        if not self._name_fetched:
            try:
                self.device_name = await self.hass.async_add_executor_job(
                    self.client.get_nickname
                )
                self._name_fetched = True
            except Exception:
                pass

        if not self._dock_features_fetched:
            # Probed once at startup — dock hardware doesn't come and go at
            # runtime, so there's no need to re-probe on every poll cycle.
            # Any failure (not just "unsupported") still counts as "tried"
            # so a flaky first poll doesn't re-probe forever.
            try:
                self.dock_features = await self.hass.async_add_executor_job(
                    self.client.get_dock_features
                )
            except Exception as exc:
                _LOGGER.debug("Dock feature probe failed: %s", exc)
            finally:
                self._dock_features_fetched = True

        try:
            data = await self.hass.async_add_executor_job(self.client.get_status)
        except Exception as exc:
            raise UpdateFailed(f"Failed to fetch vacuum status: {exc}") from exc

        try:
            data["consumables"] = await self.hass.async_add_executor_job(
                self.client.get_consumables
            )
        except Exception as exc:
            _LOGGER.debug("Consumables fetch failed: %s", exc)
            data["consumables"] = {}

        # Refresh map on first load, and every MAP_INTERVAL_ACTIVE seconds while
        # actively cleaning or every (slower) MAP_INTERVAL seconds otherwise.
        is_cleaning = VACUUM_STATES.get(data.get("status_code", 0)) == "cleaning"
        map_cycles = self._map_cycles_active if is_cleaning else self._map_cycles_idle
        self._map_tick += 1
        if self.map_image_bytes is None or self._map_tick >= map_cycles:
            self._map_tick = 0
            try:
                await self.hass.async_add_executor_job(self._refresh_map)
            except Exception as exc:
                _LOGGER.warning("Map refresh failed: %s", exc)
            try:
                await self.hass.async_add_executor_job(self._refresh_schedules)
            except Exception as exc:
                _LOGGER.debug("Schedule refresh failed: %s", exc)

        # Only updated on a map refresh (see above), so it holds the last
        # known value on poll cycles in between rather than flickering.
        data["current_room"] = self.current_room
        return data

    def _refresh_map(self) -> None:
        current_id, _ = self.client.get_map_info()
        map_data       = self.client.get_map_data(current_id)
        self.map_id    = current_id
        self.rooms     = [a for a in map_data.get("area_list", [])
                          if a.get("type") == "room"]
        self.map_image_bytes = _render_map_image(map_data)
        room = _room_at_vac(map_data)
        self.current_room = _b64name(room.get("name", "")) if room else None
        _LOGGER.debug("Map rendered: %d bytes, %d rooms, current room: %s",
                      len(self.map_image_bytes), len(self.rooms), self.current_room)

    def _refresh_schedules(self) -> None:
        room_names = {r["id"]: _b64name(r.get("name", "")) for r in self.rooms}
        raw_rules = self.client.get_schedules()
        self.schedules = [_decode_schedule(r, room_names) for r in raw_rules]
        _LOGGER.debug("Fetched %d schedule(s)", len(self.schedules))

    def resolve_rooms_live(
        self, name_patterns: list[str], map_name: str | None = None
    ) -> tuple[list[int], int]:
        """Fetch rooms live from device, resolve names → (room_ids, map_id).

        Uses map_name (partial match) if given, otherwise current map.
        Raises ValueError if map or any room is not found.
        """
        current_map_id, map_list = self.client.get_map_info()

        if map_name:
            folded_map_name = _fold(map_name)
            target_id = next(
                (m["map_id"] for m in map_list
                 if folded_map_name in _fold(_b64name(m.get("map_name", "")))),
                None,
            )
            if target_id is None:
                available = [_b64name(m.get("map_name", "")) for m in map_list]
                raise ValueError(f"Map '{map_name}' not found. Available: {available}")
        else:
            target_id = current_map_id

        map_data = self.client.get_map_data(target_id)
        rooms = [a for a in map_data.get("area_list", []) if a.get("type") == "room"]

        matched: list[int] = []
        seen: set[int] = set()
        for pat in name_patterns:
            folded_pat = _fold(pat)
            folded_names = [_fold(_b64name(r.get("name", ""))) for r in rooms]
            exact = [r for r, n in zip(rooms, folded_names) if n == folded_pat]
            hits = exact or [r for r, n in zip(rooms, folded_names) if folded_pat in n]
            if not hits:
                available = [_b64name(r.get("name", "")) for r in rooms]
                raise ValueError(f"No room matching '{pat}'. Available: {available}")
            for r in hits:
                if r["id"] not in seen:
                    seen.add(r["id"]); matched.append(r["id"])

        return matched, target_id
