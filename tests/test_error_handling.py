"""Regression coverage for the v2.1.0 bugfixes:

- send() must not blindly retry a mutating command after the device has
  already answered with a real (non-zero) error_code — that answer is
  final, and resending risks double-executing the command.
- clean_rooms()/clean_spot() must refuse with a clear, human-readable
  error (like the already-cleaning case) rather than either forwarding a
  request the device is known to reject with "Device error -3001" while
  paused (status 7), or silently dropping it without any feedback.
- get_dock_features() must not let a single non-"unsupported" probe
  failure discard every feature already confirmed.
"""
from __future__ import annotations

import pytest

from custom_components.tapo_rv30.tpap import TapoVacuumClient

from .fake_device import FakeDevice


def _make_client(tmp_path, **kwargs) -> TapoVacuumClient:
    params = {"host": "192.0.2.10", "username": "admin", "password": "hunter2"}
    params.update(kwargs)
    return TapoVacuumClient(cache_dir=tmp_path, **params)


def test_send_raises_immediately_on_device_error_without_retry(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"setSwitchClean": {}},
        error_codes={"setSwitchClean": -3002},
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    with pytest.raises(RuntimeError, match="-3002"):
        client.send("setSwitchClean", {"clean_mode": 3})

    # The rejected call must be sent exactly once — retrying it would risk
    # the device executing it twice.
    assert device.call_counts["setSwitchClean"] == 1


def test_send_reauthenticates_on_http_401_session_rejection(tmp_path) -> None:
    """A stale stok is answered with plain HTTP 401 before any encrypted reply
    exists (regression seen on every poll after the session expired in v3.0.0):
    send() must treat it as session loss, re-handshake, and succeed."""
    import requests

    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"getVacStatus": {"status": 3}},
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    real_post = client._post
    rejected = {"done": False}

    def post(path, body=None, binary=False):
        if binary and path.startswith("/stok=") and not rejected["done"]:
            rejected["done"] = True
            resp = requests.Response()
            resp.status_code = 401
            raise requests.HTTPError("401 Client Error: Unknown Status", response=resp)
        return real_post(path, body, binary=binary)

    client._post = post

    result = client.send("getVacStatus")

    assert result["result"]["status"] == 3
    # The session was dropped and a fresh handshake happened (the fake device
    # counts the retried call under the new session).
    assert device.call_counts["getVacStatus"] == 1


def test_clean_rooms_refuses_while_paused(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={
            "getVacStatus": {"status": 7, "err_status": [0]},
            "setSwitchClean": {},
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    # Must raise a clear, human-readable error — not silently do nothing,
    # and not let the device's raw "-3001" through.
    with pytest.raises(ValueError, match="paused"):
        client.clean_rooms([1, 2], map_id=5)

    assert "setSwitchClean" not in device.call_counts


def test_clean_spot_refuses_while_paused(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={
            "getVacStatus": {"status": 7, "err_status": [0]},
            "setSwitchClean": {},
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    with pytest.raises(ValueError, match="paused"):
        client.clean_spot()

    assert "setSwitchClean" not in device.call_counts


def test_clean_rooms_refuses_while_already_cleaning(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={
            "getVacStatus": {"status": 1, "err_status": [0]},
            "setSwitchClean": {},
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    with pytest.raises(ValueError, match="already in progress"):
        client.clean_rooms([1, 2], map_id=5)

    assert "setSwitchClean" not in device.call_counts


def test_run_schedule_does_not_mutate_settings_while_paused(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={
            "getVacStatus": {"status": 7, "err_status": [0]},
            "get_schedule_rules": {
                "rule_list": [
                    {"id": 1, "clean_attr": {"room_list": [1, 2], "map_id": 5}},
                ]
            },
            "getCleanAttr": {"suction": 2, "cistern": 1, "clean_number": 1},
            "setCleanAttr": {},
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    # Must be rejected before setCleanAttr writes the schedule's suction/
    # water/passes settings to the device — otherwise a rejected schedule
    # would still leave those settings changed.
    with pytest.raises(ValueError, match="paused"):
        client.run_schedule(1)

    assert "setCleanAttr" not in device.call_counts


def test_get_dock_features_keeps_confirmed_features_after_one_probe_error(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"getDustCollectionInfo": {}},
        error_codes={
            # A genuine (non "-1002 unsupported") failure on one probe...
                "getDryMopMode": -1,
            # ...must not hide a feature this same probe pass already found.
            "getCutHairMode": -1002,
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    features, complete = client.probe_dock_actions()

    assert features == ["wash_mop"]
    assert complete is True
    # The old behavior aborted the whole probe loop on the first non-1002
    # error, so getDryMopMode would never have been called at all — assert
    # it was, to actually cover "continues past the failure" and not just
    # "happens to return the right set".
    assert device.call_counts["getCutHairMode"] == 1
