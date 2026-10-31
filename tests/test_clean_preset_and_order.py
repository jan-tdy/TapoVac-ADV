"""Regression coverage for issue #53: an optional `clean_order` for `clean_rooms`'
per-run settings, and the `clean_custom_rule` locking fix needed to expose it
directly as `clean_preset` (previously only reached through `run_preset` /
`run_schedule`, which already held the session lock around their whole call)."""
from __future__ import annotations

import threading

import pytest

from custom_components.tapo_rv30 import tpap as T


def _client(tmp_path):
    c = T.TapoVacuumClient("192.0.2.1", "u", "p", cache_dir=tmp_path)
    c._session_id, c._seq, c._key, c._base_nonce = "s1", 10, b"k" * 16, b"n" * 12
    return c


def test_clean_rooms_passes_clean_order_through(tmp_path, monkeypatch):
    c = _client(tmp_path)
    calls = []

    def send(method, params=None):
        calls.append((method, params))
        if method == "getMapInfo":
            return {"result": {"current_map_id": 5, "map_list": []}}
        if method == "getVacStatus":
            return {"result": {"status": 0}}
        return {"result": {}}

    monkeypatch.setattr(c, "send", send)
    c.clean_rooms([1, 2], 5, clean_order=False)
    switch = next(p for m, p in calls if m == "setSwitchClean")
    assert switch["clean_order"] is False


def test_clean_custom_rule_sends_expected_payload(tmp_path, monkeypatch):
    c = _client(tmp_path)
    calls = []

    def send(method, params=None):
        calls.append((method, params))
        if method == "getVacStatus":
            return {"result": {"status": 0}}
        return {"result": {}}

    monkeypatch.setattr(c, "send", send)
    c.clean_custom_rule(999, 5, clean_order=False)
    switch = next(p for m, p in calls if m == "setSwitchClean")
    assert switch == {
        "clean_mode": 5, "clean_on": True, "clean_order": False,
        "force_clean": False, "map_id": 5, "custom_rule_id": 999, "start_type": 1,
    }


def test_clean_custom_rule_refuses_while_paused(tmp_path, monkeypatch):
    c = _client(tmp_path)
    monkeypatch.setattr(c, "send", lambda method, params=None: {"result": {"status": 7}})

    with pytest.raises(T.RobotBusy, match="paused"):
        c.clean_custom_rule(999, 5)


def test_clean_custom_rule_holds_the_lock_across_the_idle_check_and_start(tmp_path, monkeypatch):
    """clean_custom_rule is now @_atomic: a caller with no outer atomic wrapper of its
    own (clean_preset, unlike run_preset/run_schedule) must still get the idle check and
    the start command as one unit — another thread's send() cannot land between them."""
    c = _client(tmp_path)
    monkeypatch.setattr(c, "send", lambda method, params=None: {"result": {"status": 0}})
    done = threading.Event()

    def worker():
        c.clean_custom_rule(1, 5)
        done.set()

    with c._lock:
        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=0.2)
        assert not done.is_set(), "clean_custom_rule ran while the session lock was held elsewhere"
    t.join(timeout=1)
    assert done.is_set()
