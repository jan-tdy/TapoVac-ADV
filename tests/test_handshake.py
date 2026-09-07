"""End-to-end SPAKE2+/TPAP handshake tests: a `TapoVacuumClient` talking, via
`FakeDevice` (tests/fake_device.py), to an independently-computed device-side
SPAKE2+ responder in-process (no network). This is the "known-good transcript"
coverage requested in issue #16 for tpap.py: a regression here means the
handshake, transcript, confirmation MACs, or session-cipher derivation no
longer interoperate with a device performing the mirrored protocol math.
"""
from __future__ import annotations

import pytest

from custom_components.tapo_rv30.tpap import AuthError, TapoVacuumClient

from .fake_device import FakeDevice


def _make_client(tmp_path, **kwargs) -> TapoVacuumClient:
    params = {"host": "192.0.2.10", "username": "admin", "password": "hunter2"}
    params.update(kwargs)
    return TapoVacuumClient(cache_dir=tmp_path, **params)


# cipher_suite -> (hkdf_hash, cmac) per tpap.py's own lookup table:
#   SHA512 for {2,4,5,7,9}, CMAC for {8,9}.
CIPHER_SUITES = [1, 2, 8, 9]
ENCRYPTIONS = ["aes_128_ccm", "aes_256_ccm", "chacha20_poly1305"]


@pytest.mark.parametrize("cipher_suite", CIPHER_SUITES)
@pytest.mark.parametrize("encryption", ENCRYPTIONS)
def test_authenticate_and_send_round_trip(tmp_path, cipher_suite, encryption) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        cipher_suite=cipher_suite, encryption=encryption,
        responses={"getVacStatus": {"status": 1, "err_status": [0]}},
    )
    client = _make_client(tmp_path)
    device.attach(client)

    client.authenticate()
    assert client._session_id == device.session_id
    assert client._key and client._base_nonce

    resp = client.send("getVacStatus")
    assert resp["result"]["status"] == 1


def test_authenticate_fails_with_wrong_password(tmp_path) -> None:
    device = FakeDevice(username="admin", password="the-real-password")
    client = _make_client(tmp_path, password="wrong-password")
    device.attach(client)

    with pytest.raises(AuthError):
        client.authenticate()


def test_authenticate_fails_with_wrong_username_for_shadow_cred(tmp_path) -> None:
    # password_shadow/passwd_id=3 mixes the username into the derived
    # credential (see _build_cred), so a username mismatch alone must also
    # be caught by the confirmation check even though the raw password
    # matches.
    extra_crypt = {"type": "password_shadow", "params": {"passwd_id": 3}}
    device = FakeDevice(username="admin", password="hunter2", extra_crypt=extra_crypt)
    client = _make_client(tmp_path, username="not-admin")
    device.attach(client)

    with pytest.raises(AuthError):
        client.authenticate()


def test_get_device_info_decodes_nickname_and_reads_model(tmp_path) -> None:
    import base64
    device = FakeDevice(username="admin", password="hunter2", responses={
        "getDeviceInfo": {
            "nickname": base64.b64encode("Living Room Bot".encode()).decode(),
            "model": "RV50 Pro Omni",
            "hw_ver": "1.0", "fw_ver": "1.2.3",
        },
    })
    client = _make_client(tmp_path)
    device.attach(client)

    assert client.get_device_info() == {"nickname": "Living Room Bot", "model": "RV50 Pro Omni"}


def test_get_device_info_defaults_when_model_field_missing(tmp_path) -> None:
    device = FakeDevice(username="admin", password="hunter2", responses={
        "getDeviceInfo": {"nickname": ""},
    })
    client = _make_client(tmp_path)
    device.attach(client)

    info = client.get_device_info()
    assert info["model"] == ""
    assert info["nickname"] == "Tapo RV30"  # empty nickname falls back too


def test_get_status_maps_all_fields(tmp_path) -> None:
    device = FakeDevice(username="admin", password="hunter2", responses={
        "getVacStatus": {"status": 2, "err_status": [7]},
        "getBatteryInfo": {"battery_percentage": 55},
        "getCleanInfo": {"clean_area": 12, "clean_time": 300, "clean_percent": 40},
        "getCleanAttr": {"suction": 3, "cistern": 2, "clean_number": 1},
        "getMopState": {"mop_state": True},
    })
    client = _make_client(tmp_path)
    device.attach(client)

    status = client.get_status()

    assert status == {
        "status_code": 2,
        "error_codes": [7],
        "battery": 55,
        "suction": 3,
        "cistern": 2,
        "clean_number": 1,
        "mop_attached": True,
        "clean_area": 12,
        "clean_time": 300,
        "clean_percent": 40,
    }


def test_session_cache_round_trip_avoids_a_second_handshake(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"getVacStatus": {"status": 0, "err_status": [0]}},
    )
    first = _make_client(tmp_path)
    device.attach(first)
    first.authenticate()

    # A fresh client instance pointed at the same cache dir/host/user should
    # load the persisted session instead of re-authenticating.
    second = _make_client(tmp_path)
    assert second._load_session() is True
    assert second._session_id == first._session_id
    assert second._key == first._key
    assert second._base_nonce == first._base_nonce

    device.attach(second)
    resp = second.send("getVacStatus")
    assert resp["result"]["status"] == 0
