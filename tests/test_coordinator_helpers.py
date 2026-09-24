"""Tests for the map/name helpers in coordinator.py."""
from __future__ import annotations

import base64

import pytest
import requests
from homeassistant.core import HomeAssistant

from custom_components.tapo_rv30 import coordinator as coordinator_module
from custom_components.tapo_rv30.coordinator import (
    TapoCoordinator,
    _b64name,
    _fold,
    _render_map_image,
    _room_at_vac,
)

from .helpers import encode_lz4_literal_block


def test_coordinator_starts_with_generic_device_model() -> None:
    # Regression test for issue #36: before the device's real model is
    # fetched (or if getDeviceInfo never returns one), device_info must show
    # a generic placeholder rather than a hardcoded specific model string.
    coordinator = TapoCoordinator(HomeAssistant(), client=object())
    assert coordinator.device_model == "Tapo Robot Vacuum"
    assert coordinator.device_name == "Tapo RV30"


def test_b64name_decodes_utf8() -> None:
    raw = base64.b64encode("Kúpeľňa".encode()).decode()
    assert _b64name(raw) == "Kúpeľňa"


def test_b64name_returns_original_on_bad_input() -> None:
    assert _b64name("not-valid-base64!!") == "not-valid-base64!!"


def test_fold_strips_diacritics_and_lowercases() -> None:
    assert _fold("Kúpeľňa") == "kupelna"
    assert _fold("ŽIVOT") == "zivot"


def _make_map_data(width: int, height: int, pixels: bytes, *, vac=None, charge=None,
                    area_list=None) -> dict:
    return {
        "width": width,
        "height": height,
        "pix_len": len(pixels),
        "map_data": base64.b64encode(encode_lz4_literal_block(pixels)).decode(),
        "vac_coor": vac,
        "charge_coor": charge,
        "area_list": area_list or [],
    }


def test_room_at_vac_finds_matching_room() -> None:
    # 4x4 grid; row-major, row 0 = bottom of real space (per _render_map_image
    # comment). Put room id 5 at grid (x=2, y=1) -> pixel index 1*4+2 = 6.
    pixels = bytearray([255] * 16)
    pixels[1 * 4 + 2] = 5
    map_data = _make_map_data(4, 4, bytes(pixels), vac=[2, 1],
                               area_list=[{"type": "room", "id": 5, "name": "room"}])

    room = _room_at_vac(map_data)

    assert room is not None
    assert room["id"] == 5


def test_room_at_vac_none_when_vac_coor_missing() -> None:
    map_data = _make_map_data(4, 4, bytes([255] * 16))
    assert _room_at_vac(map_data) is None


def test_room_at_vac_none_when_out_of_bounds() -> None:
    map_data = _make_map_data(4, 4, bytes([255] * 16), vac=[10, 10])
    assert _room_at_vac(map_data) is None


def test_room_at_vac_none_when_pixel_has_no_matching_room() -> None:
    # vac sits on plain floor (255); area_list only has a room at a
    # different id, so no room claims this pixel.
    pixels = bytearray([255] * 16)
    map_data = _make_map_data(4, 4, bytes(pixels), vac=[0, 0],
                               area_list=[{"type": "room", "id": 9, "name": "room"}])
    assert _room_at_vac(map_data) is None


def test_render_map_image_produces_jpeg_bytes() -> None:
    pixels = bytearray([255] * 16)  # all floor
    pixels[5] = 1  # one room pixel
    map_data = _make_map_data(
        4, 4, bytes(pixels),
        vac=[1, 1], charge=[0, 0],
        area_list=[{"type": "room", "id": 1, "name": base64.b64encode(b"Room A").decode()}],
    )

    img_bytes, geometry = _render_map_image(map_data)

    assert isinstance(img_bytes, bytes)
    assert img_bytes[:2] == b"\xff\xd8"  # JPEG SOI marker
    assert isinstance(geometry, dict)


class _FlakyClient:
    """Fake client whose get_status() fails a set number of times with a
    transport-level connection error before succeeding (or exhausts)."""

    def __init__(self, fail_times: int, exc: Exception | None = None) -> None:
        self.fail_times = fail_times
        self.exc = exc or requests.exceptions.ConnectionError("Host is unreachable")
        self.calls = 0

    def get_status(self) -> dict:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return {"status_code": 0}


def test_get_status_with_retry_recovers_from_transient_connection_error(monkeypatch) -> None:
    # Regression test: a brief network blip (stale ARP entry, missed Wi-Fi
    # wake) shouldn't fail the whole poll if the device answers again within
    # a couple of retries.
    monkeypatch.setattr(coordinator_module.time, "sleep", lambda _seconds: None)
    client = _FlakyClient(fail_times=2)
    coordinator = TapoCoordinator(HomeAssistant(), client=client)

    result = coordinator._get_status_with_retry()

    assert result == {"status_code": 0}
    assert client.calls == 3


def test_get_status_with_retry_raises_after_exhausting_retries(monkeypatch) -> None:
    monkeypatch.setattr(coordinator_module.time, "sleep", lambda _seconds: None)
    client = _FlakyClient(fail_times=99)
    coordinator = TapoCoordinator(HomeAssistant(), client=client)

    with pytest.raises(requests.exceptions.ConnectionError):
        coordinator._get_status_with_retry()

    # Exactly one initial attempt plus one per configured retry delay — no
    # more, no less.
    assert client.calls == 1 + len(coordinator_module.STATUS_RETRY_DELAYS)


def test_get_status_with_retry_does_not_retry_non_connection_errors(monkeypatch) -> None:
    # A device-level error (e.g. RuntimeError from tpap.send()) is a real
    # answer, not a transport hiccup — retrying it here would just delay
    # surfacing it, and risks masking a genuine device problem as a network
    # one.
    monkeypatch.setattr(coordinator_module.time, "sleep", lambda _seconds: None)
    client = _FlakyClient(fail_times=1, exc=RuntimeError("Device error -1002"))
    coordinator = TapoCoordinator(HomeAssistant(), client=client)

    with pytest.raises(RuntimeError, match="-1002"):
        coordinator._get_status_with_retry()

    assert client.calls == 1
