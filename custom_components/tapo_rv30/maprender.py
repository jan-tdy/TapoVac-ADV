"""Map rendering: LZ4 pixel grid -> annotated image with room/map geometry.
No Home Assistant imports."""
from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageDraw, ImageFont

from .const import (
    CARPET_COLOR,
    FLOOR_COLOR,
    FORBID_COLOR,
    FORBID_OUTLINE,
    FURNITURE_OUTLINE,
    FURNITURE_TYPES,
    ROOM_PALETTE,
    UNKNOWN_COLOR,
    VIRTUAL_WALL_COLOR,
    WALL_COLOR,
    ZONE_OUTLINE,
)
from .mapdata import b64name, decode_path, lz4_block_decompress, mm_to_grid, validate_map

MAP_SCALE = 4   # px per vacuum grid cell -> ~700x700 output image
FONT_SIZE = 14


def _font(size: int = FONT_SIZE):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


# Furniture: our own little illustrations, defined in the unit square of each item's
# rectangle (a across its width, b down its height) and mapped onto the item's rotated
# outline, so the robot's angle comes for free. Shapes are drawn on a 2x overlay and
# downsampled, which is what makes the curves smooth.
#   ("rrect", a0, b0, a1, b1, radius, fill, outline)   rounded rectangle
#   ("ellipse", ca, cb, ra, rb, fill, outline)          ra, rb in width / height units
#   ("poly", [(a, b), ...], fill, outline)
#   ("line", [(a, b), ...], colour, width)
WOOD, WOOD_D = (211, 201, 184), (145, 132, 111)
FABRIC, FABRIC_D = (202, 201, 197), (128, 127, 123)
LINEN, LINEN_D = (218, 216, 211), (145, 143, 137)
STEEL, STEEL_D = (204, 211, 217), (124, 135, 145)
LEAF, LEAF_D = (191, 202, 184), (119, 133, 110)
CERAMIC, CERAMIC_D = (246, 248, 252), (130, 140, 160)
PET, PET_D = (246, 214, 180), (170, 120, 70)
PILLOW = (252, 252, 255)


def _bed(double: bool):
    pillows = ([("rrect", 0.10, 0.06, 0.47, 0.24, 0.05, PILLOW, LINEN_D), ("rrect", 0.53, 0.06, 0.90, 0.24, 0.05, PILLOW, LINEN_D)]
               if double else [("rrect", 0.16, 0.06, 0.84, 0.24, 0.05, PILLOW, LINEN_D)])
    return [("rrect", 0, 0, 1, 1, 0.08, LINEN, LINEN_D), ("rrect", 0, 0, 1, 0.05, 0.02, LINEN_D, LINEN_D),
            *pillows, ("rrect", 0.04, 0.30, 0.96, 0.97, 0.06, (200, 190, 230), LINEN_D),
            ("line", [(0.04, 0.42), (0.96, 0.42)], LINEN_D, 1)]


def _sofa(seats: int, corner: bool = False):
    g = [("rrect", 0, 0, 1, 1, 0.12, FABRIC, FABRIC_D), ("rrect", 0.02, 0.02, 0.98, 0.30, 0.10, FABRIC_D, FABRIC_D),
         ("rrect", 0.0, 0.25, 0.13, 1.0, 0.08, FABRIC_D, FABRIC_D), ("rrect", 0.87, 0.25, 1.0, 1.0, 0.08, FABRIC_D, FABRIC_D)]
    w = (0.87 - 0.13) / seats
    for i in range(seats):
        g.append(("rrect", 0.13 + i * w + 0.015, 0.33, 0.13 + (i + 1) * w - 0.015, 0.96, 0.06, (228, 222, 214), FABRIC_D))
    if corner:
        g.append(("rrect", 0.13, 0.55, 0.50, 0.96, 0.06, (228, 222, 214), FABRIC_D))
    return g


def _chairs():
    pts = [(0.03, 0.30), (0.03, 0.56), (0.83, 0.30), (0.83, 0.56), (0.30, 0.02), (0.56, 0.02), (0.30, 0.82), (0.56, 0.82)]
    return [("rrect", a, b, a + 0.14, b + 0.16, 0.04, WOOD_D, WOOD_D) for a, b in pts]


FURNITURE_GLYPHS = {
    1:   _bed(False),
    2:   _bed(True),
    101: _sofa(1),
    102: _sofa(2),
    103: _sofa(3, corner=True),
    201: _chairs() + [("rrect", 0.17, 0.20, 0.83, 0.80, 0.08, WOOD, WOOD_D), ("line", [(0.22, 0.5), (0.78, 0.5)], WOOD_D, 1)],
    202: [("rrect", 0.08, 0.08, 0.92, 0.92, 0.10, WOOD, WOOD_D), ("line", [(0.14, 0.5), (0.86, 0.5)], WOOD_D, 1)],
    203: [("rrect", 0.08, 0.08, 0.92, 0.92, 0.12, WOOD, WOOD_D), ("ellipse", 0.5, 0.5, 0.16, 0.16, (255, 244, 200), WOOD_D)],
    204: [("rrect", 0.05, 0.05, 0.95, 0.95, 0.08, WOOD, WOOD_D), ("line", [(0.5, 0.08), (0.5, 0.92)], WOOD_D, 1)],
    205: [("rrect", 0.08, 0.08, 0.92, 0.92, 0.12, WOOD, WOOD_D), ("rrect", 0.08, 0.08, 0.92, 0.22, 0.06, WOOD_D, WOOD_D)],
    301: [("rrect", 0.04, 0.10, 0.96, 0.90, 0.06, WOOD, WOOD_D), ("rrect", 0.12, 0.20, 0.88, 0.80, 0.03, WOOD_D, WOOD_D)],
    302: [("rrect", 0, 0, 1, 1, 0.05, WOOD, WOOD_D), ("line", [(0.5, 0.04), (0.5, 0.96)], WOOD_D, 1),
          ("ellipse", 0.44, 0.5, 0.03, 0.05, WOOD_D, WOOD_D), ("ellipse", 0.56, 0.5, 0.03, 0.05, WOOD_D, WOOD_D)],
    303: [("rrect", 0.06, 0.06, 0.94, 0.94, 0.10, WOOD, WOOD_D), ("ellipse", 0.5, 0.5, 0.18, 0.18, (255, 244, 200), WOOD_D)],
    401: [("rrect", 0, 0, 1, 1, 0.08, STEEL, STEEL_D), ("line", [(0.04, 0.36), (0.96, 0.36)], STEEL_D, 1),
          ("rrect", 0.82, 0.10, 0.88, 0.30, 0.02, STEEL_D, STEEL_D), ("rrect", 0.82, 0.42, 0.88, 0.80, 0.02, STEEL_D, STEEL_D)],
    402: [("rrect", 0.04, 0.04, 0.96, 0.96, 0.08, STEEL, STEEL_D), ("rrect", 0.10, 0.06, 0.90, 0.16, 0.03, STEEL_D, STEEL_D)],
    403: [("rrect", 0.08, 0.08, 0.92, 0.92, 0.10, STEEL, STEEL_D), ("line", [(0.08, 0.30), (0.92, 0.30)], STEEL_D, 1)],
    503: [("ellipse", 0.5, 0.78, 0.26, 0.18, (186, 120, 80), (120, 70, 40)),
          ("ellipse", 0.36, 0.42, 0.26, 0.28, LEAF, LEAF_D), ("ellipse", 0.64, 0.42, 0.26, 0.28, LEAF, LEAF_D),
          ("ellipse", 0.5, 0.30, 0.26, 0.26, (160, 212, 140), LEAF_D)],
    601: [("rrect", 0.12, 0.0, 0.88, 0.34, 0.06, CERAMIC, CERAMIC_D), ("ellipse", 0.5, 0.66, 0.36, 0.32, CERAMIC, CERAMIC_D),
          ("ellipse", 0.5, 0.66, 0.24, 0.20, (214, 226, 240), CERAMIC_D)],
    602: [("rrect", 0.04, 0.10, 0.96, 0.90, 0.10, CERAMIC, CERAMIC_D), ("ellipse", 0.5, 0.56, 0.34, 0.28, (214, 226, 240), CERAMIC_D),
          ("ellipse", 0.5, 0.18, 0.05, 0.05, CERAMIC_D, CERAMIC_D)],
    701: [("rrect", 0.06, 0.06, 0.94, 0.94, 0.10, PET, PET_D), ("line", [(0.5, 0.06), (0.5, 0.94)], PET_D, 1),
          ("rrect", 0.36, 0.06, 0.64, 0.24, 0.04, (120, 80, 60), PET_D)],
    702: [("rrect", 0.04, 0.04, 0.96, 0.96, 0.10, (200, 210, 220), STEEL_D), ("rrect", 0.12, 0.14, 0.88, 0.90, 0.08, PET, PET_D),
          ("ellipse", 0.32, 0.40, 0.05, 0.05, PET_D, PET_D), ("ellipse", 0.58, 0.32, 0.05, 0.05, PET_D, PET_D),
          ("ellipse", 0.50, 0.68, 0.05, 0.05, PET_D, PET_D), ("ellipse", 0.70, 0.72, 0.05, 0.05, PET_D, PET_D)],
    703: [("ellipse", 0.28, 0.5, 0.24, 0.40, STEEL, STEEL_D), ("ellipse", 0.28, 0.5, 0.15, 0.25, (120, 150, 190), STEEL_D),
          ("ellipse", 0.72, 0.5, 0.24, 0.40, STEEL, STEEL_D), ("ellipse", 0.72, 0.5, 0.15, 0.25, PET, PET_D)],
}
_SS = 2   # supersampling factor for the furniture overlay


def _unit_rrect(a0, b0, a1, b1, r, steps=5):
    """Rounded-rectangle outline in unit coordinates (radius r in width units)."""
    r = min(r, (a1 - a0) / 2, (b1 - b0) / 2)
    pts = []
    for cx, cy, start in ((a1 - r, b0 + r, -90), (a1 - r, b1 - r, 0), (a0 + r, b1 - r, 90), (a0 + r, b0 + r, 180)):
        for i in range(steps + 1):
            t = math.radians(start + 90 * i / steps)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def _draw_furniture(img: Image.Image, furniture: list[dict], to_px) -> None:
    """Draw muted, unlabelled furniture silhouettes in each item's rotated bounds."""
    W, H = img.size
    overlay = Image.new("RGBA", (W * _SS, H * _SS), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for f in furniture:
        verts = f.get("vertexs") or []
        if len(verts) < 4:
            continue
        p0, p1, _, p3 = [to_px(x, y) for x, y in verts[:4]]

        def at(a: float, b: float):
            return ((p0[0] + a * (p1[0] - p0[0]) + b * (p3[0] - p0[0])) * _SS,
                    (p0[1] + a * (p1[1] - p0[1]) + b * (p3[1] - p0[1])) * _SS)

        shapes = FURNITURE_GLYPHS.get(f.get("type")) or [("rrect", 0, 0, 1, 1, 0.06, (236, 236, 240), FURNITURE_OUTLINE)]
        for shape in shapes:
            kind = shape[0]
            if kind == "rrect":
                _, a0, b0, a1, b1, r, fill, outline = shape
                od.polygon([at(a, b) for a, b in _unit_rrect(a0, b0, a1, b1, r)], fill=(*fill, 255), outline=(*outline, 255), width=_SS)
            elif kind == "ellipse":
                _, ca, cb, ra, rb, fill, outline = shape
                od.polygon([at(ca + ra * math.cos(t), cb + rb * math.sin(t)) for t in (i * math.pi / 16 for i in range(32))],
                           fill=(*fill, 255), outline=(*outline, 255), width=_SS)
            elif kind == "poly":
                _, pts, fill, outline = shape
                od.polygon([at(a, b) for a, b in pts], fill=(*fill, 255), outline=(*outline, 255), width=_SS)
            elif kind == "line":
                _, pts, colour, width = shape
                od.line([at(a, b) for a, b in pts], fill=(*colour, 255), width=width * _SS)
    img.alpha_composite(overlay.resize((W, H), Image.Resampling.LANCZOS))


def _px_transform(map_data: dict):
    """Return mm -> image px function for this map (Y grows upwards in the grid,
    downwards in the image)."""
    height = map_data["height"]

    def to_px(x_mm: float, y_mm: float) -> tuple[float, float]:
        gx, gy = mm_to_grid(map_data, x_mm, y_mm)
        return gx * MAP_SCALE + MAP_SCALE / 2, (height - 1 - gy) * MAP_SCALE + MAP_SCALE / 2

    return to_px


def _grid_px(gx: float, gy: float, height: int) -> tuple[int, int]:
    return int(gx * MAP_SCALE + MAP_SCALE // 2), int((height - 1 - gy) * MAP_SCALE + MAP_SCALE // 2)


def vacuum_position_grid(map_data: dict, docked: bool = False) -> tuple[float, float] | None:
    """Find a valid robot position, preferring grid coordinates over real-world mm.

    Firmware sometimes omits ``vac_coor`` while still returning ``real_vac_coor``;
    when docked, it may only report the charging-base coordinate. Keep trying the
    available representations so one missing field cannot hide the map marker.
    """
    width, height = map_data.get("width"), map_data.get("height")
    try:
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return None

    candidates = [(map_data.get("vac_coor"), False), (map_data.get("real_vac_coor"), True)]
    if docked:
        candidates.extend(((map_data.get("charge_coor"), False),
                           (map_data.get("real_charge_coor"), True)))
    for point, is_mm in candidates:
        try:
            x, y = float(point[0]), float(point[1])
            if not math.isfinite(x) or not math.isfinite(y):
                continue
            if is_mm:
                x, y = mm_to_grid(map_data, x, y)
        except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
            continue
        if 0 <= x < width and 0 <= y < height:
            return x, y
    return None


# The live cleaning path is drawn as the strip the robot's head actually covered,
# not just a hairline: a translucent grey swath as wide as the vacuum (~33 cm)
# with the thin blue line down its centre.
VAC_WIDTH_MM = 330
PATH_SWEEP_COLOR = (150, 150, 155, 110)
MAX_PATH_OVERLAY_PIXELS = 16_000_000


def _sweep_width_px(resolution) -> int:
    """Width in px of the strip the robot's head covers (~33 cm)."""
    return max(2, round(VAC_WIDTH_MM / (resolution or 50) * MAP_SCALE))


def draw_clean_path(img: Image.Image, to_px, points: list, resolution, line_fill=(0, 140, 220, 200),
                    line_width: int = 2) -> Image.Image:
    """Draw the area the robot swept (grey swath as wide as its head) with the
    driven path down the middle. Returns a new image; img is left untouched."""
    if len(points) < 2:
        return img
    px = [to_px(x, y) for x, y in points]
    sweep = _sweep_width_px(resolution)
    # Restrict work to the path bounds and split large bounds into padded tiles.
    # Even a 1x full-map overlay would need 256 MiB at the maximum map size.
    pad = max(sweep / 2, line_width / 2) + 2
    left = max(0, math.floor(min(x for x, _ in px) - pad))
    top = max(0, math.floor(min(y for _, y in px) - pad))
    right = min(img.width, math.ceil(max(x for x, _ in px) + pad) + 1)
    bottom = min(img.height, math.ceil(max(y for _, y in px) + pad) + 1)
    if right <= left or bottom <= top:
        return img

    ss = 3
    img = img.convert("RGBA")

    def draw_layer(fill, width):
        # Include a stroke-width margin around each core tile so downsampling
        # has neighboring pixels and seams do not appear between tiles.
        margin = math.ceil(width / 2) + 2
        max_side = math.isqrt(MAX_PATH_OVERLAY_PIXELS)
        core_size = max(1, max_side // ss - 2 * margin)
        scaled_width = max(1, round(width * ss))
        radius = scaled_width / 2
        for core_top in range(top, bottom, core_size):
            core_bottom = min(bottom, core_top + core_size)
            for core_left in range(left, right, core_size):
                core_right = min(right, core_left + core_size)
                tile_left = max(0, core_left - margin)
                tile_top = max(0, core_top - margin)
                tile_right = min(img.width, core_right + margin)
                tile_bottom = min(img.height, core_bottom + margin)
                tile_w, tile_h = tile_right - tile_left, tile_bottom - tile_top
                overlay = Image.new("RGBA", (tile_w * ss, tile_h * ss), (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                scaled = [((x - tile_left) * ss, (y - tile_top) * ss) for x, y in px]
                draw.line(scaled, fill=fill, width=scaled_width, joint="curve")
                # Explicit round joins keep tight turns solid across tiles.
                for sx, sy in scaled:
                    draw.ellipse((sx - radius, sy - radius, sx + radius, sy + radius), fill=fill)
                overlay = overlay.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
                box = (tile_left, tile_top, tile_right, tile_bottom)
                composed = Image.alpha_composite(img.crop(box), overlay)
                core = composed.crop((core_left - tile_left, core_top - tile_top,
                                      core_right - tile_left, core_bottom - tile_top))
                img.paste(core, (core_left, core_top))

    draw_layer(PATH_SWEEP_COLOR, sweep)
    draw_layer(line_fill, line_width)
    return img


def render_map(map_data: dict, draw_furniture: bool = False) -> tuple[Image.Image, list[dict], dict]:
    """Decode the LZ4 pixel grid and draw rooms, no-go zones, virtual walls,
    carpets, saved zones, furniture, labels and the dock.

    draw_furniture=False keeps the furniture glyphs off the image: the geometry
    is still returned in map_geometry for cards that draw it themselves.

    Returns (base image without the vacuum marker, room_geometry, map_geometry).
    room_geometry: per room id/name, bbox and centre in image px.
    map_geometry: dimensions and coordinate transforms for map actions (mm -> px).
    """
    validate_map(map_data)
    width, height, pix_len = map_data["width"], map_data["height"], map_data["pix_len"]
    pixels = lz4_block_decompress(base64.b64decode(map_data["map_data"]), pix_len)

    areas = map_data.get("area_list", [])
    rooms = [a for a in areas if a.get("type") == "room"]
    sorted_ids = sorted(r["id"] for r in rooms)
    room_colors = {rid: ROOM_PALETTE[i % len(ROOM_PALETTE)] for i, rid in enumerate(sorted_ids)}

    lut: list[tuple[int, int, int]] = [UNKNOWN_COLOR] * 256
    lut[0] = WALL_COLOR
    lut[127] = UNKNOWN_COLOR
    lut[255] = FLOOR_COLOR
    for rid, color in room_colors.items():
        if 0 <= rid <= 255:
            lut[rid] = color

    # Paint the grid at 1 px per cell, then scale: far faster than per-cell rectangles.
    # Unknown area is transparent so the map sits on light and dark themes alike.
    small = Image.new("RGBA", (width, height))
    small.putdata([(*lut[p], 255) if (p < 256 and p != 127) else (0, 0, 0, 0) for p in pixels])
    small = small.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    img = small.resize((width * MAP_SCALE, height * MAP_SCALE), Image.Resampling.NEAREST)

    to_px = _px_transform(map_data)

    def poly(a: dict) -> list[tuple[float, float]]:
        return [to_px(x, y) for x, y in a.get("vertexs", [])]

    draw = ImageDraw.Draw(img)
    for a in areas:
        if a.get("type") == "carpet_rectangle" and len(a.get("vertexs", [])) >= 3:
            draw.polygon(poly(a), fill=CARPET_COLOR, outline=(170, 170, 170))
    if draw_furniture:
        _draw_furniture(img, map_data.get("furniture_list", []), to_px)
    draw = ImageDraw.Draw(img)
    for a in areas:
        if a.get("type") == "area" and len(a.get("vertexs", [])) >= 3:
            draw.polygon(poly(a), outline=ZONE_OUTLINE, width=2)

    # Translucent no-go zones need an RGBA pass.
    forbid = [a for a in areas if a.get("type") == "forbid" and len(a.get("vertexs", [])) >= 3]
    if forbid:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for a in forbid:
            od.polygon(poly(a), fill=FORBID_COLOR, outline=FORBID_OUTLINE + (255,), width=2)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
    for a in areas:
        if a.get("type") == "virtual_wall" and len(a.get("vertexs", [])) >= 2:
            draw.line(poly(a), fill=VIRTUAL_WALL_COLOR, width=3)

    # Room geometry (bbox / centroid in image px) and labels.
    font = _font()
    geometry: list[dict] = []
    cells: dict[int, list[tuple[int, int]]] = {rid: [] for rid in room_colors}
    for row in range(height):
        base = row * width
        for col in range(width):
            pv = pixels[base + col]
            if pv in cells:
                cells[pv].append((col, row))
    for room in rooms:
        rid = room["id"]
        pts = cells.get(rid) or []
        if not pts:
            continue
        xs = [c for c, _ in pts]
        ys = [r for _, r in pts]
        cx, cy = _grid_px(sum(xs) / len(xs), sum(ys) / len(ys), height)
        x0, y0 = _grid_px(min(xs), max(ys), height)
        x1, y1 = _grid_px(max(xs), min(ys), height)
        raw_name = b64name(room.get("name", "")).strip()
        name = raw_name if raw_name else f"Room {rid}"
        geometry.append({"id": rid, "name": name, "bbox": [x0, y0, x1, y1], "centre": [cx, cy],
                         "cells": len(pts), "suction": room.get("suction"), "water_level": room.get("cistern"),
                         "passes": room.get("clean_number")})
        draw.text((cx + 1, cy + 1), name, fill=(0, 0, 0), font=font, anchor="mm")
        draw.text((cx, cy), name, fill=(255, 255, 255), font=font, anchor="mm")

    charge = map_data.get("charge_coor")
    if charge:
        _draw_dock(img, *_grid_px(charge[0], charge[1], height),
                   resolution=map_data.get("resolution"))

    zones = [{"id": a.get("id"), "px": [list(p) for p in poly(a)],
              "mm": [list(v) for v in a.get("vertexs", [])],
              "suction": a.get("suction"), "water_level": a.get("cistern"), "passes": a.get("clean_number")}
             for a in areas if a.get("type") == "area" and len(a.get("vertexs", [])) >= 3]
    furniture = [{"id": f.get("id"), "type": f.get("type"),
                  "type_name": FURNITURE_TYPES.get(f.get("type")), "angle": f.get("angle"),
                  "px": [list(p) for p in poly(f)], "mm": [list(v) for v in f.get("vertexs", [])]}
                 for f in map_data.get("furniture_list", []) if len(f.get("vertexs", [])) >= 3]
    map_geometry = {
        "map_id": map_data.get("map_id"),
        "saved_zones": zones,
        "furniture": furniture,
        "map_name": b64name(map_data.get("map_name", "")),
        "image_size": [img.width, img.height],
        "grid_size": [width, height],
        "scale_px_per_cell": MAP_SCALE,
        "resolution_mm": map_data.get("resolution"),
        "real_origin_mm": list((map_data.get("real_origin_coor") or [0, 0])[:2]),
        # px_x = ((mm_x - ox) / res) * scale + scale / 2
        # px_y = (grid_h - 1 - (mm_y - oy) / res) * scale + scale / 2
        "dock_px": list(_grid_px(charge[0], charge[1], height)) if charge else None,
    }
    return img, geometry, map_geometry


CLEANED_COLOR = (88, 170, 255)
RECORD_FLOOR = (205, 205, 210)


def render_record(rec: dict) -> Image.Image:
    """A finished run from getCleanRecordExtraInfo: cells the robot cleaned (255)
    in blue over the rooms it skipped in grey, with the path it drove, where it
    started (green) and where it stopped (red). Same grid format as the live map."""
    validate_map(rec)
    width, height, pix_len = rec["width"], rec["height"], rec["pix_len"]
    pixels = lz4_block_decompress(base64.b64decode(rec["map_data"]), pix_len)
    lut: list[tuple[int, int, int]] = [RECORD_FLOOR] * 256
    lut[0] = WALL_COLOR
    lut[255] = CLEANED_COLOR
    small = Image.new("RGBA", (width, height))
    small.putdata([(*lut[p], 255) if (p < 256 and p != 127) else (0, 0, 0, 0) for p in pixels])
    small = small.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    img = small.resize((width * MAP_SCALE, height * MAP_SCALE), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(img)
    to_px = _px_transform(rec)
    for a in rec.get("area_list", []):
        if a.get("type") == "forbid" and len(a.get("vertexs", [])) >= 3:
            draw.polygon([to_px(x, y) for x, y in a["vertexs"]], outline=FORBID_OUTLINE, width=2)
    pts: list = []
    if rec.get("pos_array") and rec.get("pos_len"):
        try:
            pts = decode_path(rec["pos_array"], int(rec["pos_len"]))
        except Exception:
            pts = []
    if len(pts) > 1:
        draw.line([to_px(x, y) for x, y in pts], fill=(20, 60, 140, 220), width=2, joint="curve")
        _dot(draw, *map(int, to_px(*pts[0])), (40, 180, 90), 5)
        _dot(draw, *map(int, to_px(*pts[-1])), (220, 60, 60), 5)
    charge = rec.get("real_charge_coor")
    if charge:
        _draw_dock(img, *map(int, to_px(charge[0], charge[1])),
                   resolution=rec.get("resolution"))
    return img


def _dot(draw: ImageDraw.ImageDraw, sx: int, sy: int, color, radius: int = 6) -> None:
    draw.ellipse([sx - radius, sy - radius, sx + radius, sy + radius],
                 fill=color, outline=(255, 255, 255), width=2)


# Map markers drawn like the integration logo: the robot is a disc in the
# logo's own palette, the dock a small plate. Both go on a supersampled
# overlay so the curves stay smooth at the map's small marker sizes.
_MARKER_SS = 4
VACUUM_BODY = (248, 250, 252)     # logo's near-white face
VACUUM_RIM = (51, 181, 238)       # logo's blue ring
VACUUM_TRIM = (150, 200, 228)
DOCK_BODY = (228, 231, 236)
DOCK_EDGE = (120, 126, 136)


def _marker_canvas(img: Image.Image, cx: float, cy: float, half: float):
    """A supersampled tile covering only this marker, plus a coordinate mapper
    and the function that folds the tile back into img.

    Supersampling the whole map to draw one small marker cost ~300 ms per poll
    (a 4x overlay of the full image, resized back down); a tile the size of the
    marker itself is ~0.1 ms. Clipped to the image so a marker parked off the
    map edge composites cleanly instead of raising.
    """
    s = _MARKER_SS
    pad = 2                                   # room for the drop shadow / AA edge
    x0 = max(0, int(cx - half - pad))
    y0 = max(0, int(cy - half - pad))
    x1 = min(img.size[0], int(cx + half + pad) + 1)
    y1 = min(img.size[1], int(cy + half + pad) + 1)
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    ov = Image.new("RGBA", (tw * s, th * s), (0, 0, 0, 0))

    def commit() -> None:
        img.alpha_composite(ov.resize((tw, th), Image.Resampling.LANCZOS), dest=(x0, y0))

    def at(px: float, py: float) -> tuple[float, float]:
        return (px - x0) * s, (py - y0) * s

    return ImageDraw.Draw(ov), commit, s, at


def _draw_vacuum(img: Image.Image, sx: int, sy: int, resolution=None, radius: int | None = None) -> None:
    """Where the robot is, as the logo's disc: blue rim, light face and a small
    lidar dome. Sized to the strip its head sweeps, so the marker and the grey
    swath read as one object — the robot sits exactly inside its own trail."""
    if radius is None:
        # Match the trace's physical 330 mm width exactly (rather than rounding
        # the half-width down); the minimum keeps the marker visible on tiny maps.
        radius = max(1, _sweep_width_px(resolution) / 2)
    draw, commit, s, at = _marker_canvas(img, sx, sy, radius + 1)
    cx, cy = at(sx, sy)
    r = radius * s
    # drop shadow, then the rim ring and the face inside it
    draw.ellipse([cx - r + s / 2, cy - r + s / 2, cx + r + s / 2, cy + r + s / 2],
                 fill=(0, 0, 0, 60))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 43, 57, 255))
    outer = max(0.5, r - max(1, int(0.10 * r)))
    draw.ellipse([cx - outer, cy - outer, cx + outer, cy + outer], fill=(*VACUUM_RIM, 255))
    face = max(0.5, outer - max(1, int(0.28 * r)))
    draw.ellipse([cx - face, cy - face, cx + face, cy + face], fill=(*VACUUM_BODY, 255))
    # lidar dome, offset towards the front, kept small so the face still reads
    dr = max(0.5, face * 0.30)
    dy = cy - int(face * 0.26)
    draw.ellipse([cx - dr, dy - dr, cx + dr, dy + dr],
                 fill=(*VACUUM_TRIM, 255), outline=(*VACUUM_RIM, 255), width=max(1, s // 2))
    commit()


def _draw_dock(img: Image.Image, sx: int, sy: int, resolution=None,
               width: int | None = None, height: int | None = None) -> None:
    """The charging base: a small plate with a status LED, centred on its
    coordinate (the vacuum parks front-first into it). Scaled off the swept
    strip like the robot is, but kept clearly smaller than it."""
    if width is None:
        width = max(9, round(_sweep_width_px(resolution) * 0.62))
    if height is None:
        height = max(6, round(width * 0.68))
    draw, commit, s, at = _marker_canvas(img, sx, sy, max(width, height) / 2 + 1)
    cx, cy = at(sx, sy)
    w, h = width * s / 2, height * s / 2
    draw.rectangle([cx - w + s / 2, cy - h + s / 2, cx + w + s / 2, cy + h + s / 2],
                   fill=(0, 0, 0, 60))
    draw.rectangle([cx - w, cy - h, cx + w, cy + h],
                   fill=(*DOCK_BODY, 255), outline=(*DOCK_EDGE, 255), width=max(1, s))
    # status LED: one small dot, so the plate isn't a bare grey box
    lr = max(1, int(0.16 * h))
    ly = cy - h * 0.36
    draw.ellipse([cx - lr, ly - lr, cx + lr, ly + lr], fill=(110, 220, 130, 255))
    commit()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


_jpeg = _png   # kept for callers; the map is PNG with transparency since 0.11
