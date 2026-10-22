"""Coverage for the v3.2.0 read-only info getters.

Method names come from python-kasa's vacuum component table
(devtools/helpers/smartrequests.py — "speaker" component) and the method
dump in python-kasa issue #937, never from probing a live device (an
unknown method name can factory-reset it), so these tests pin down the
request names and the defensive parsing against the fake device.
"""
from __future__ import annotations

import pytest

from custom_components.tapo_rv30.tpap import TapoVacuumClient

from .fake_device import FakeDevice


def _connected(tmp_path, **kwargs) -> tuple[TapoVacuumClient, FakeDevice]:
    device = FakeDevice(username="admin", password="hunter2", **kwargs)
    client = TapoVacuumClient(
        cache_dir=tmp_path, host="192.0.2.10", username="admin", password="hunter2")
    device.attach(client)
    client.authenticate()
    return client, device


def test_get_device_time_returns_raw_result(tmp_path) -> None:
    client, device = _connected(
        tmp_path, responses={"getDeviceTime": {"time": 1760000000, "time_diff": 120}})
    assert client.get_device_time() == {"time": 1760000000, "time_diff": 120}
    assert device.call_counts["getDeviceTime"] == 1


def test_get_wireless_connected_status_returns_raw_result(tmp_path) -> None:
    client, device = _connected(
        tmp_path, responses={"getWirelessConnectedStatus": {"connected": True}})
    assert client.get_wireless_connected_status() == {"connected": True}
    assert device.call_counts["getWirelessConnectedStatus"] == 1


def test_get_auto_dust_collection_returns_raw_result(tmp_path) -> None:
    client, _ = _connected(
        tmp_path, responses={"getAutoDustCollection": {"auto_dust_collection": True}})
    assert client.get_auto_dust_collection() == {"auto_dust_collection": True}


def test_voice_language_merges_both_calls(tmp_path) -> None:
    client, device = _connected(tmp_path, responses={
        "getSupportVoiceLanguage": {"support_language": ["en", "sk"]},
        "getCurrentVoiceLanguage": {"language": "en"},
    })
    assert client.get_voice_language() == {
        "support": {"support_language": ["en", "sk"]},
        "current": {"language": "en"},
    }
    assert device.call_counts["getSupportVoiceLanguage"] == 1
    assert device.call_counts["getCurrentVoiceLanguage"] == 1


def test_voice_language_survives_one_unsupported_call(tmp_path) -> None:
    """Firmware without the speaker component answers UNKNOWN_METHOD to one
    of the two calls; the other one must still come through."""
    client, _ = _connected(
        tmp_path,
        responses={"getCurrentVoiceLanguage": {"language": "sk"}},
        error_codes={"getSupportVoiceLanguage": -3001},
    )
    assert client.get_voice_language() == {"current": {"language": "sk"}}


def test_plain_info_getters_surface_device_error(tmp_path) -> None:
    """The non-voice getters must raise on a device error — diagnostics turns
    it into a visible {"error": ...} entry instead of dropping it silently."""
    client, _ = _connected(tmp_path, error_codes={"getDeviceTime": -3001})
    with pytest.raises(RuntimeError, match="-3001"):
        client.get_device_time()
