"""Tests for the low-level crypto/encoding helpers in tpap.py: the HKDF
wrapper, SEC1 point (de)serialization, the SPAKE2+ integer-to-octet-string
`w` encoding, credential derivation, nonce construction, and the JSON
session-cache (de)serialization.

`_hkdf`/`_hkdf_expand` are checked against an independent, from-scratch
RFC 5869 HKDF implementation (built here from `hmac`/`hashlib`, not by
importing any third-party HKDF), rather than trusting the same
`cryptography`-backed implementation under test to grade itself.
"""
from __future__ import annotations

import hashlib
import hmac
import struct

import pytest

from custom_components.tapo_rv30 import tpap


# ---------------------------------------------------------------------------
# Independent reference HKDF (RFC 5869), used only to check tpap._hkdf.
# ---------------------------------------------------------------------------
def _ref_hkdf(ikm: bytes, salt: bytes, info: bytes, length: int, hash_name: str) -> bytes:
    hashmod = getattr(hashlib, hash_name)
    hlen = hashmod().digest_size
    salt = salt or b"\x00" * hlen
    prk = hmac.new(salt, ikm, hashmod).digest()
    okm = b""
    t = b""
    counter = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashmod).digest()
        okm += t
        counter += 1
    return okm[:length]


@pytest.mark.parametrize("algo, hash_name", [("SHA256", "sha256"), ("SHA512", "sha512")])
@pytest.mark.parametrize("length", [16, 32, 48, 64])
def test_hkdf_matches_reference_implementation(algo: str, hash_name: str, length: int) -> None:
    master = b"\x01\x02\x03" * 5
    salt = b"salt-value"
    info = b"info-context"
    assert tpap._hkdf(master, salt=salt, info=info, length=length, algo=algo) == \
        _ref_hkdf(master, salt, info, length, hash_name)


@pytest.mark.parametrize("algo, hash_name", [("SHA256", "sha256"), ("SHA512", "sha512")])
def test_hkdf_expand_matches_reference_implementation(algo: str, hash_name: str) -> None:
    prk = b"pseudorandom-key-material-1234567890"
    dlen = 32
    got = tpap._hkdf_expand("SomeLabel", prk, dlen, algo)
    expected = _ref_hkdf(prk, b"\x00" * dlen, b"SomeLabel", dlen, hash_name)
    assert got == expected


def test_hkdf_output_depends_on_salt_and_info() -> None:
    master = b"same-master-secret"
    a = tpap._hkdf(master, salt=b"salt-a", info=b"info", length=32, algo="SHA256")
    b = tpap._hkdf(master, salt=b"salt-b", info=b"info", length=32, algo="SHA256")
    c = tpap._hkdf(master, salt=b"salt-a", info=b"other-info", length=32, algo="SHA256")
    assert len({a, b, c}) == 3


# ---------------------------------------------------------------------------
# SEC1 point (de)serialization
# ---------------------------------------------------------------------------
def test_sec1_roundtrip_on_p256_constants() -> None:
    # _P256_M/_P256_N are stored in *compressed* SEC1 form (0x02/0x03
    # prefix); _xy_unc always re-encodes as *uncompressed* (0x04 prefix), so
    # the round trip is on the coordinates, not the raw bytes.
    for point in (tpap._P256_M, tpap._P256_N):
        x, y = tpap._sec1_xy(point)
        uncompressed = tpap._xy_unc(x, y)
        assert uncompressed[0] == 0x04
        x2, y2 = tpap._sec1_xy(uncompressed)
        assert (x2, y2) == (x, y)


# ---------------------------------------------------------------------------
# SPAKE2+ `w` integer encoding
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "w, expected",
    [
        (0, b"\x00"),
        (0x7F, b"\x7f"),          # high bit clear -> no padding
        (0x80, b"\x00\x80"),      # high bit set, odd length -> zero-padded
        (0xFF, b"\x00\xff"),
        (0x100, b"\x01\x00"),     # even length already -> no padding needed
    ],
)
def test_encode_w_known_values(w: int, expected: bytes) -> None:
    assert tpap._encode_w(w) == expected


@pytest.mark.parametrize("w", [1, 2, 255, 256, 65535, 65536, 2**200, 2**255])
def test_encode_w_round_trips_the_integer(w: int) -> None:
    assert int.from_bytes(tpap._encode_w(w), "big") == w


# ---------------------------------------------------------------------------
# Nonce construction
# ---------------------------------------------------------------------------
def test_nonce_replaces_last_4_bytes_with_big_endian_seq() -> None:
    base = bytes(range(12))
    out = tpap._nonce(base, 0x01020304)
    assert out[:8] == base[:8]
    assert out[8:] == struct.pack(">I", 0x01020304)
    assert len(out) == 12


# ---------------------------------------------------------------------------
# Credential PBKDF2 derivation
# ---------------------------------------------------------------------------
def test_derive_ab_is_deterministic_and_salt_sensitive() -> None:
    cred = b"admin/hunter2"
    a1, b1 = tpap._derive_ab(cred, b"salt-one", 100)
    a2, b2 = tpap._derive_ab(cred, b"salt-one", 100)
    a3, b3 = tpap._derive_ab(cred, b"salt-two", 100)
    assert (a1, b1) == (a2, b2)
    assert (a1, b1) != (a3, b3)


# ---------------------------------------------------------------------------
# _build_cred branches
# ---------------------------------------------------------------------------
def test_build_cred_plain_user_and_password() -> None:
    assert tpap._build_cred({}, "admin", "hunter2", "aabbccddeeff") == "admin/hunter2"
    assert tpap._build_cred({}, "", "hunter2", "aabbccddeeff") == "hunter2"


def test_build_cred_password_shadow_id2_is_sha1_of_password() -> None:
    extra = {"type": "password_shadow", "params": {"passwd_id": 2}}
    assert tpap._build_cred(extra, "admin", "hunter2", "aabbccddeeff") == \
        hashlib.sha1(b"hunter2").hexdigest()


def test_build_cred_password_shadow_id3_uses_md5_user_and_mac() -> None:
    extra = {"type": "password_shadow", "params": {"passwd_id": 3}}
    mac12 = "aabbccddeeff"
    got = tpap._build_cred(extra, "admin", "hunter2", mac12)
    mac_colon = "AA:BB:CC:DD:EE:FF"
    expected = hashlib.sha1((hashlib.md5(b"admin").hexdigest() + "_" + mac_colon).encode()).hexdigest()
    assert got == expected


def test_build_cred_password_shadow_id3_falls_back_without_valid_mac() -> None:
    extra = {"type": "password_shadow", "params": {"passwd_id": 3}}
    assert tpap._build_cred(extra, "admin", "hunter2", "") == "hunter2"


def test_build_cred_password_sha_with_salt() -> None:
    import base64
    salt = "s0m3salt"
    extra = {
        "type": "password_sha_with_salt",
        "params": {"sha_name": 0, "sha_salt": base64.b64encode(salt.encode()).decode()},
    }
    got = tpap._build_cred(extra, "admin", "hunter2", "aabbccddeeff")
    assert got == hashlib.sha256(("admin" + salt + "hunter2").encode()).hexdigest()


def test_build_cred_password_sha_with_salt_user_name_variant() -> None:
    import base64
    salt = "xyz"
    extra = {
        "type": "password_sha_with_salt",
        "params": {"sha_name": 1, "sha_salt": base64.b64encode(salt.encode()).decode()},
    }
    got = tpap._build_cred(extra, "admin", "hunter2", "aabbccddeeff")
    assert got == hashlib.sha256(("user" + salt + "hunter2").encode()).hexdigest()


def test_build_cred_password_sha_with_salt_bad_salt_falls_back() -> None:
    extra = {"type": "password_sha_with_salt", "params": {"sha_name": 0, "sha_salt": "!!!not-b64!!!"}}
    assert tpap._build_cred(extra, "admin", "hunter2", "aabbccddeeff") == "hunter2"


def test_build_cred_unknown_type_falls_back_to_plain() -> None:
    extra = {"type": "something_else", "params": {}}
    assert tpap._build_cred(extra, "admin", "hunter2", "aabbccddeeff") == "admin/hunter2"


# ---------------------------------------------------------------------------
# Session cache (de)serialization
# ---------------------------------------------------------------------------
def test_cache_encode_decode_round_trip() -> None:
    original = {
        "host": "10.0.0.5",
        "user": "admin",
        "mac": "aabbccddeeff",
        "pake": [2],
        "sid": "session-123",
        "seq": 42,
        "cid": "aes_128_ccm",
        "hkdf": "SHA256",
        "key": b"\x01\x02\x03\x04" * 4,
        "nonce": b"\x05\x06\x07\x08" * 3,
    }
    decoded = tpap._cache_decode(tpap._cache_encode(original))
    assert decoded == original
