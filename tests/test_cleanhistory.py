"""Clean map history: what is kept of a run, that it draws the same, and retention."""
import base64
import gzip
import json
import struct

from custom_components.tapo_rv30 import cleanhistory as ch
from custom_components.tapo_rv30.maprender import render_record

from .helpers import encode_lz4_literal_block

DAY = 86400


def _pos_array(points: list[tuple[int, int]]) -> tuple[str, int]:
    body = b"\x00" * 8 + b"".join(struct.pack(">hh", x, y) for x, y in points)
    return base64.b64encode(encode_lz4_literal_block(body)).decode(), len(body)


def _record() -> dict:
    pixels = bytes([255] * 16)
    pos_array, pos_len = _pos_array([(0, 0), (100, 50), (200, 100)])
    return {
        "width": 4, "height": 4, "pix_len": len(pixels),
        "map_data": base64.b64encode(encode_lz4_literal_block(pixels)).decode(),
        "resolution": 50, "real_origin_coor": [0, 0],
        "pos_array": pos_array, "pos_len": pos_len,
        "real_charge_coor": [300, 0, 0],
        "area_list": [{"type": "forbid", "vertexs": [[0, 0], [100, 0], [100, 100]]},
                      {"type": "room", "id": 1, "vertexs": []}],
        "room_list": [{"id": 1, "suction": 2}] * 50,      # not needed to draw: not kept
    }


def test_slim_keeps_what_drawing_needs_and_draws_the_same():
    rec = _record()
    small = ch.slim(rec)
    assert "room_list" not in small and "furniture_list" not in small
    assert [a["type"] for a in small["area_list"]] == ["forbid"]
    assert render_record(small).tobytes() == render_record(rec).tobytes()


def test_add_get_list_and_no_rewrite(tmp_path):
    h = ch.CleanHistory(str(tmp_path / "robot"))
    meta = {"area": 13, "minutes": 11, "map_id": 9, "map_name": "Downstairs", "start_type": 1, "secret": "x"}
    assert h.add(1000, meta, _record())
    assert not h.add(1000, meta, _record())             # already kept
    [entry] = h.entries()
    assert entry["started"] == 1000 and entry["area"] == 13 and "secret" not in entry and entry["bytes"] > 0
    assert render_record(h.get(1000)).size == render_record(_record()).size
    assert h.get(2000) is None and h.has(1000) and not h.has(2000)
    assert h.usage() == {"runs": 1, "bytes": entry["bytes"]}


def test_index_survives_damage_and_hand_edits(tmp_path):
    folder = tmp_path / "robot"
    h = ch.CleanHistory(str(folder))
    h.add(1000, {"area": 1}, _record())
    h.add(2000, {"area": 2}, _record())
    (folder / "index.json").write_text("{not json")
    (folder / "1000.json.gz").unlink()                   # removed by hand
    with gzip.open(folder / "3000.json.gz", "wt") as fh:  # copied in without an index entry
        json.dump({"meta": {"started": 3000, "area": 3}, "map": ch.slim(_record())}, fh)
    fresh = ch.CleanHistory(str(folder))
    assert [e["started"] for e in fresh.entries()] == [3000, 2000]


def test_prune_by_age_and_count(tmp_path):
    h = ch.CleanHistory(str(tmp_path / "robot"))
    now = 100 * DAY
    for d in (1, 5, 20, 40, 95):
        h.add(int(now - d * DAY), {}, _record())
    assert h.prune(now, 30, 200) == 2                    # 40 and 95 days old
    assert h.prune(now, None, 2) == 1                    # only the newest two stay
    assert [e["started"] for e in h.entries()] == [now - DAY, now - 5 * DAY]
    assert h.prune(now, ch.retention_days("Off"), 200) == 2   # Off keeps nothing
    assert h.entries() == [] and not list((tmp_path / "robot").glob("*.json.gz"))
    h.add(int(now + DAY), {}, _record())                   # the robot's clock ahead of this one
    assert h.prune(now, 0, 200) == 1


def test_retention_labels():
    assert ch.retention_days("Forever") is None and ch.retention_days("1 week") == 7
    assert ch.retention_days("nonsense") == ch.retention_days(ch.DEFAULT_RETENTION)


def test_missing_folder_is_empty(tmp_path):
    h = ch.CleanHistory(str(tmp_path / "nothing"))
    assert h.entries() == [] and h.prune(0, 0, 10) == 0 and not h.delete(5)
