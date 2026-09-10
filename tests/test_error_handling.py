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


def test_get_dock_features_keeps_confirmed_features_after_one_probe_error(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"getDustCollectionInfo": {}},
        error_codes={
            # A genuine (non "-1002 unsupported") failure on one probe...
            "getBackWashMode": -1,
            # ...must not hide a feature this same probe pass already found.
            "getDryMopMode": -1002,
            "getCutHairMode": -1002,
        },
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    features = client.get_dock_features()

    assert features == {"dust_collection"}
