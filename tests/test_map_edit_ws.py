"""Tests for the map editor's furniture read-after-write verification."""
from __future__ import annotations

from custom_components.tapo_rv30.mapdata import vertexs_match


def test_vertexs_match_within_grid_snapping_tolerance() -> None:
    sent = [[0, 0], [900, 0], [900, 900], [0, 900]]
    kept = [[10, -5], [905, 3], [895, 910], [-8, 895]]  # snapped by a few mm
    assert vertexs_match(sent, kept)


def test_vertexs_match_false_when_robot_kept_the_old_shape() -> None:
    # Regression: a rotate/move the robot silently ignores while keeping the
    # item's id must be caught, not just an outright missing id.
    sent = [[0, 0], [900, 0], [900, 900], [0, 900]]       # the new, rotated shape
    kept = [[0, 0], [0, 900], [-900, 900], [-900, 0]]     # the robot kept the old one
    assert not vertexs_match(sent, kept)


def test_vertexs_match_false_when_missing_or_mismatched_length() -> None:
    assert not vertexs_match(None, [[0, 0]])
    assert not vertexs_match([[0, 0]], None)
    assert not vertexs_match([[0, 0], [1, 1]], [[0, 0]])
