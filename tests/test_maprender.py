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
