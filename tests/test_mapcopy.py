"""Copying a map / restoring a backup as a new map: the backup re-id and a fresh map id
(pure, no Home Assistant). Ported from upstream tapo-rv30-ha's test_mapcopy.py, trimmed to the
pieces this fork's mapbackup/mapcopy modules implement (see mapcopy.py's docstring for why the
"carrier" put-back logic is not carried over)."""
import gzip
import hashlib
import io
import json
import tarfile

import pytest

from custom_components.tapo_rv30 import mapbackup, mapcopy

OLD = 1792568378
PREFIX = bytes.fromhex("4d5a905e741f534ba1f8f7c918df8ff07d6eaa550200000020")
ROOMS = [{"name": "SGFsbHdheQ==", "color": 3, "type": "room", "id": 4, "suction": 4},
         {"name": "S2l0Y2hlbg==", "color": 2, "type": "room", "id": 2, "carpet_strategy": 1}]
FURNITURE = [{"id": 0, "type": 201, "angle": 0, "vertexs": [[-2051, 567], [152, 567], [152, -604]]}]


def _area(map_id):
    return json.dumps({"areas": [], "mapId": map_id, "singleRoom": False}, indent="\t").replace(
        '"mapId": ', '"mapId" : ').encode()


def _bkmap(map_id=OLD, tail=None):
    """A backup in the robot's exact layout (as read from real RV30 Max Plus backups)."""
    files = {"path_map": bytes(24) + OLD.to_bytes(8, "little") + bytes(16),
             "map.gridmap": bytes(300) + map_id.to_bytes(8, "little"),
             "area_user.json": _area(map_id), "area_info.json": _area(map_id),
             "navmap_bound.json": b'{"navmap_min_x": -1, "navmap_max_x": 1, "navmap_min_y": -1, "navmap_max_y": 1}'}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, raw in files.items():
            ti = tarfile.TarInfo("./" + name)
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
    gz = gzip.compress(buf.getvalue())
    t = json.dumps(tail if tail is not None else
                   {"real_origin_coor": [-7425, -4625, 0], "area_list": ROOMS, "furniture_list": FURNITURE}).encode()
    return (PREFIX + hashlib.md5(gz).hexdigest().encode() + b"\x01" + len(gz).to_bytes(4, "big") + gz
            + b"\x03" + len(t).to_bytes(4, "big") + t)


def test_reid_changes_only_the_map_id():
    data = _bkmap()
    out = mapbackup.reid_bkmap(data, 1792933921)
    a, b = mapbackup.parse_bkmap(data), mapbackup.parse_bkmap(out)
    assert mapbackup.map_id_of(data) == OLD and mapbackup.map_id_of(out) == 1792933921
    assert a["tail"] == b["tail"]
    assert a["members"]["path_map"] == b["members"]["path_map"]          # not part of the map's id
    for name in ("area_info.json", "area_user.json"):
        assert json.loads(b["members"][name])["mapId"] == 1792933921
        assert b["members"][name].replace(b"1792933921", str(OLD).encode()) == a["members"][name]
    # header: the fixed prefix, md5 of the new gzip member and its length
    size = int.from_bytes(out[58:62], "big")
    assert out[:25] == PREFIX and out[57] == 1
    assert out[25:57] == hashlib.md5(out[62:62 + size]).hexdigest().encode()
    assert out[62 + size:] == data[62 + int.from_bytes(data[58:62], "big"):]   # tail byte for byte


def test_reid_refuses_what_it_does_not_understand():
    data = _bkmap()
    with pytest.raises(ValueError, match="version 2"):
        mapbackup.reid_bkmap(b"MZ" + data[2:10] + bytes(5) + data[15:], 1792933921)
    broken = bytearray(data)
    broken[100] ^= 0xFF                                                  # payload no longer matches its md5
    with pytest.raises(ValueError, match="damaged"):
        mapbackup.reid_bkmap(bytes(broken), 1792933921)
    with pytest.raises(ValueError, match="already has"):
        mapbackup.reid_bkmap(data, OLD)
    with pytest.raises(ValueError, match="digits"):
        mapbackup.reid_bkmap(data, 123456789)


def test_reid_rejects_short_or_truncated_input():
    data = _bkmap()
    with pytest.raises(ValueError):
        mapbackup.reid_bkmap(data[:40], 1792933921)
    size = int.from_bytes(data[58:62], "big")
    cut = data[:62 + size - 20]
    head = cut[:25] + hashlib.md5(cut[62:]).hexdigest().encode() + b"\x01" + (size - 20).to_bytes(4, "big")
    with pytest.raises(ValueError):
        mapbackup.reid_bkmap(head + cut[62:], 1792933921)


def test_new_map_id_is_the_time_and_never_taken():
    assert mapcopy.new_map_id({OLD: "Downstairs"}, 1792933921.7) == 1792933921
    assert mapcopy.new_map_id({1792933921, 1792933922}, 1792933921) == 1792933923
    with pytest.raises(ValueError):
        mapcopy.new_map_id(set(), 2**31)


def test_map_id_of_missing_grid_is_none():
    data = _bkmap()
    parsed = mapbackup.parse_bkmap(data)
    parsed["members"].pop("map.gridmap")
    assert mapbackup._id_in(parsed["members"]) is None
