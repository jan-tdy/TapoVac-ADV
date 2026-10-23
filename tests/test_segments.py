"""vacuum.clean_area segment-id resolution (`mapdata.resolve_segments`).

Home Assistant's area mapping accumulates segment ids for as long as the
areas are mapped: remaps and re-pairings leave the previous map's ids in
place, and ids from before the v2.6.0 "<map>:<room>" format are plain room
numbers. vacuum.clean_area forwards every mapped id, so the handler must
drop what the vacuum no longer knows instead of failing the whole call."""
from __future__ import annotations

import pytest

from custom_components.tapo_rv30.mapdata import resolve_segments

# a two-map vacuum: map 100 (rooms 1, 2) and map 200 (rooms 5, 6)
VALID = {(100, 1), (100, 2), (200, 5), (200, 6)}


def test_valid_single_map_groups_by_map():
    assert resolve_segments(["100:1", "100:2"], VALID, 100) == {100: [1, 2]}


def test_stale_plain_ids_are_dropped():
    # pre-v2.6.0 plain ids ("1") must not raise "Unknown segment id" anymore
    assert resolve_segments(["1", "3", "100:1"], VALID, 100) == {100: [1]}


def test_ids_of_deleted_maps_are_dropped():
    assert resolve_segments(["999:1", "100:2"], VALID, 100) == {100: [2]}


def test_unknown_room_on_known_map_is_dropped():
    assert resolve_segments(["100:99", "100:1"], VALID, 100) == {100: [1]}


def test_multi_map_prefers_the_active_map():
    # the request spans two maps but the vacuum is on map 200: clean that one
    assert resolve_segments(["100:1", "200:5"], VALID, 200) == {200: [5]}


def test_multi_map_without_active_map_returns_all():
    # the caller raises its "different maps" validation error
    assert resolve_segments(["100:1", "200:5"], VALID, None) == {100: [1], 200: [5]}


def test_repaired_mapping_picks_the_right_room():
    # the real-world jedalen mapping: a plain id plus four maps' ids;
    # after the re-pair the vacuum only knows the last map
    mapping = ["1", "1778325676:1", "1788969704:5", "1792673001:5", "1792767702:1"]
    assert resolve_segments(mapping, {(1792767702, 1)}, 1792767702) == {1792767702: [1]}


def test_all_stale_raises_value_error():
    with pytest.raises(ValueError):
        resolve_segments(["1", "3", "999:1"], VALID, 100)


def test_empty_request_raises_value_error():
    with pytest.raises(ValueError):
        resolve_segments([], VALID, 100)


def test_malformed_id_is_dropped_not_fatal():
    assert resolve_segments(["100:1:2", "junk", "", "100:2"], VALID, 100) == {100: [2]}
