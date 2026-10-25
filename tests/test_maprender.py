"""Regression tests for map overlay rendering."""
from __future__ import annotations

from PIL import Image

from custom_components.tapo_rv30 import maprender


def test_clean_path_overlay_is_cropped_to_path_bounds(monkeypatch) -> None:
    image = Image.new("RGBA", (1000, 1000), (255, 255, 255, 255))
    allocated_sizes = []
    real_new = maprender.Image.new

    def record_new(mode, size, color=0):
        allocated_sizes.append(size)
        return real_new(mode, size, color)

    monkeypatch.setattr(maprender.Image, "new", record_new)

    result = maprender.draw_clean_path(
        image, lambda x, y: (x, y), [(400, 400), (410, 410)], resolution=50
    )

    assert result.size == image.size
    assert allocated_sizes
    assert all(width < image.width and height < image.height for width, height in allocated_sizes)
    assert all(width * height <= maprender.MAX_PATH_OVERLAY_PIXELS for width, height in allocated_sizes)


def test_large_clean_path_uses_tiles_within_overlay_budget(monkeypatch) -> None:
    budget = 65_536
    monkeypatch.setattr(maprender, "MAX_PATH_OVERLAY_PIXELS", budget)
    allocated_sizes = []
    real_new = maprender.Image.new

    def record_new(mode, size, color=0):
        allocated_sizes.append(size)
        return real_new(mode, size, color)

    monkeypatch.setattr(maprender.Image, "new", record_new)

    class VirtualImage:
        width = height = 512

        def convert(self, mode):
            return self

        def crop(self, box):
            return real_new("RGBA", (box[2] - box[0], box[3] - box[1]), (255, 255, 255, 255))

        def paste(self, image, xy):
            pass

    image = VirtualImage()
    result = maprender.draw_clean_path(
        image, lambda x, y: (x, y), [(0, 0), (511, 511)], resolution=50
    )

    assert result is image
    assert len(allocated_sizes) > 2  # both layers were split into multiple tiles
    assert all(width * height <= budget for width, height in allocated_sizes)


def test_furniture_overlay_is_cropped_to_item_bounds(monkeypatch) -> None:
    # Regression test: draw_furniture defaults on (v6.0.0b1+), so this runs on every
    # render for anyone with furniture placed - it must not supersample the whole map
    # (that cost ~300 ms per poll back when the vacuum/dock markers did it the same way).
    image = Image.new("RGBA", (1000, 1000), (255, 255, 255, 255))
    allocated_sizes = []
    real_new = maprender.Image.new

    def record_new(mode, size, color=0):
        allocated_sizes.append(size)
        return real_new(mode, size, color)

    monkeypatch.setattr(maprender.Image, "new", record_new)

    furniture = [{"type": 202, "vertexs": [[0, 0], [900, 0], [900, 900], [0, 900]]}]
    maprender._draw_furniture(image, furniture, lambda x, y: (x / 10, y / 10))

    assert allocated_sizes
    assert all(width < image.width and height < image.height for width, height in allocated_sizes)


def test_furniture_overlay_scales_with_item_count_not_map_size(monkeypatch) -> None:
    # A few small items, however large the map, should allocate a small, bounded amount
    # of overlay pixels in total - not grow with the map's own size.
    image = Image.new("RGBA", (4000, 4000), (255, 255, 255, 255))
    allocated_sizes = []
    real_new = maprender.Image.new

    def record_new(mode, size, color=0):
        allocated_sizes.append(size)
        return real_new(mode, size, color)

    monkeypatch.setattr(maprender.Image, "new", record_new)

    furniture = [{"type": 202, "vertexs": [[i * 2000, 0], [i * 2000 + 900, 0],
                                            [i * 2000 + 900, 900], [i * 2000, 900]]} for i in range(3)]
    maprender._draw_furniture(image, furniture, lambda x, y: (x / 10, y / 10))

    assert allocated_sizes
    assert all(width * height < 200 * 200 for width, height in allocated_sizes)


def test_draw_furniture_alpha_makes_the_glyph_see_through() -> None:
    # The live map redraws furniture a second time, on top of the vacuum/path overlay, at
    # a reduced alpha so a robot/trail under it still shows through (matches the official
    # app) - the composited pixel must actually blend with what's underneath, not just
    # look identical to a full-alpha draw.
    furniture = [{"type": 202, "vertexs": [[0, 0], [900, 0], [900, 900], [0, 900]]}]
    to_px = lambda x, y: (x / 10, y / 10)

    opaque = Image.new("RGBA", (200, 200), (10, 20, 200, 255))   # a "robot" coloured background
    maprender._draw_furniture(opaque, furniture, to_px, alpha=1.0)

    translucent = Image.new("RGBA", (200, 200), (10, 20, 200, 255))
    maprender._draw_furniture(translucent, furniture, to_px, alpha=0.5)

    # Somewhere inside the furniture's footprint, the half-alpha draw must let the
    # background colour show through more than the full-alpha one does.
    assert opaque.getpixel((45, 45)) != translucent.getpixel((45, 45))


def test_vacuum_position_grid_prefers_the_dock_while_docked() -> None:
    # Regression: vac_coor/real_vac_coor can still be the robot's last pre-dock position
    # (seen in the field: the marker sitting mid-room on an otherwise-docked robot) - while
    # docked, the dock's own coordinate must win over a stale vacuum one, not just be a
    # last-resort fallback. from_dock (the 3rd element) must say which one was picked.
    map_data = {"width": 100, "height": 100, "vac_coor": [40, 40], "charge_coor": [10, 10]}
    assert maprender.vacuum_position_grid(map_data, docked=True) == (10, 10, True)
    assert maprender.vacuum_position_grid(map_data, docked=False) == (40, 40, False)


def test_vacuum_position_grid_falls_back_to_vac_coor_if_docked_has_none() -> None:
    map_data = {"width": 100, "height": 100, "vac_coor": [40, 40]}
    assert maprender.vacuum_position_grid(map_data, docked=True) == (40, 40, False)


def test_dock_marker_offset_is_positive_and_scales_with_resolution() -> None:
    # Regression: centred on the dock, the vacuum marker (sweep-width diameter) is wider
    # than the dock plate on every side and hides it completely - this offset is what
    # moves it clear, so it must never collapse to zero.
    assert maprender.dock_marker_offset_px(50) > 0
    assert maprender.dock_marker_offset_px(20) > maprender.dock_marker_offset_px(50)
