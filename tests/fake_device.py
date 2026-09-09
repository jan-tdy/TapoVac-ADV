"""An independent SPAKE2+/TPAP responder used to test TapoVacuumClient
against, in place of a real device.

This implements the *device* side of the handshake from scratch (its own
ephemeral scalar, its own transcript computation, its own confirmation MAC),
mirroring what tpap.py's client side does but performing the mirrored math
directly rather than importing it, so a transcript/derivation bug on the
client side has a real chance of being caught here instead of the fake device
simply reproducing the same bug. It intentionally reuses tpap.py's small
generic primitives (SEC1 point (de)serialization, HKDF/HMAC/CMAC wrappers,
`_l8`, `_encode_w`, cipher key/nonce derivation) since those are
protocol-agnostic building blocks, not the SPAKE2+-specific logic being
tested — same reasoning as using the stdlib's own struct/json here.

The point is end-to-end protocol interop coverage: message shapes, transcript
construction, confirmation-MAC matching, and the encrypted request/response
transport — not an independent reimplementation of a general PAKE library.
"""
from __future__ import annotations

import json
import os
import secrets
import struct

from ecdsa import NIST256p, ellipticcurve

from custom_components.tapo_rv30 import tpap


class FakeDevice:
    """Simulates one Tapo RV30's TPAP endpoint for a single client session."""

    def __init__(
        self,
        *,
        username: str,
        password: str,
        mac: str = "AABBCCDDEEFF",
        cipher_suite: int = 1,
        encryption: str = "aes_128_ccm",
        iterations: int = 101,
        extra_crypt: dict | None = None,
        pake_type: int = 2,  # 2 = "userpw" (see TapoVacuumClient.authenticate)
        responses: dict[str, dict] | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.mac = mac
        self.cipher_suite = cipher_suite
        self.encryption = encryption
        self.iterations = iterations
        self.extra_crypt = extra_crypt or {}
        self.pake_type = pake_type
        # method name -> canned "result" payload for encrypted send() calls.
        self.responses = responses or {}

        self._hkdf_hash = "SHA512" if cipher_suite in (2, 4, 5, 7, 9) else "SHA256"
        self._cmac = cipher_suite in (8, 9)
        self._dev_salt = os.urandom(16)
        self._dev_random = os.urandom(32)
        self._ur: str | None = None
        self._w = self._h = None
        self._y = None
        self._R_enc: bytes | None = None
        self.session_id = "fake-session-id"
        self.start_seq = 1
        self._cipher_id: str | None = None
        self._key: bytes | None = None
        self._base_nonce: bytes | None = None

    # ---- request dispatch ---------------------------------------------------
    def handle_post(self, path: str, body: dict | None, *, binary: bool = False):
        if binary:
            return self._handle_encrypted(path, body)
        assert path == "/", path
        sub = (body.get("params") or {}).get("sub_method")
        if sub == "discover":
            return {"result": {"mac": self.mac, "tpap": {"pake": [self.pake_type]}}}
        if sub == "pake_register":
            return self._pake_register(body["params"])
        if sub == "pake_share":
            return self._pake_share(body["params"])
        raise AssertionError(f"unexpected sub_method {sub!r}")

    # ---- handshake ------------------------------------------------------------
    def _pake_register(self, params: dict) -> dict:
        self._ur = params["user_random"]
        # `self.encryption` is picked at construction time (parametrized by
        # tests) and returned as-is — a real device would choose one from the
        # client's offered list, but which one it picks isn't protocol logic
        # under test here.

        mac12 = self.mac.replace(":", "").replace("-", "")
        cred = tpap._build_cred(self.extra_crypt, self.username, self.password, mac12)
        order = NIST256p.generator.order()
        a, b = tpap._derive_ab(cred.encode(), self._dev_salt, self.iterations)
        self._w, self._h = a % order, b % order
        self._y = secrets.randbelow(order - 1) + 1

        G = NIST256p.generator
        curve = NIST256p.curve
        Nx, Ny = tpap._sec1_xy(tpap._P256_N)
        N = ellipticcurve.Point(curve, Nx, Ny, order)
        R = self._y * G + self._w * N
        self._R_enc = tpap._xy_unc(R.x(), R.y())

        return {"result": {
            "cipher_suites": self.cipher_suite,
            "iterations": self.iterations,
            "encryption": self.encryption,
            "extra_crypt": self.extra_crypt,
            "dev_salt": tpap._b64e(self._dev_salt),
            "dev_random": tpap._b64e(self._dev_random),
            "dev_share": tpap._b64e(self._R_enc),
        }}

    def _pake_share(self, params: dict) -> dict:
        order = NIST256p.generator.order()
        curve = NIST256p.curve
        G = NIST256p.generator

        L_enc = tpap._b64d(params["user_share"])
        u_conf_client = tpap._b64d(params["user_confirm"])

        Lx, Ly = tpap._sec1_xy(L_enc)
        L_pt = ellipticcurve.Point(curve, Lx, Ly, order)
        Mx, My = tpap._sec1_xy(tpap._P256_M)
        M = ellipticcurve.Point(curve, Mx, My, order)
        Nx, Ny = tpap._sec1_xy(tpap._P256_N)

        # Undo the client's M-blinding to recover its ephemeral point (x*G),
        # then combine with our own ephemeral y — same shared point x*y*G
        # the client derives as x*(R - w*N).
        Lp = L_pt + (-(self._w * M))
        Z = self._y * Lp
        Z_enc = tpap._xy_unc(Z.x(), Z.y())
        # V = h*y*G, computed directly from our own y (no need for the
        # client's share at all) — equals the client's h*(R-w*N)=h*y*G.
        V = self._h * (self._y * G)
        V_enc = tpap._xy_unc(V.x(), V.y())

        hfn = tpap._sha512 if self._hkdf_hash == "SHA512" else tpap._sha256
        ctx = hfn(tpap._PAKE_CTX + tpap._b64d(self._ur) + self._dev_random)
        trans = (tpap._l8(ctx) + tpap._l8(b"") + tpap._l8(b"")
                 + tpap._l8(tpap._xy_unc(Mx, My)) + tpap._l8(tpap._xy_unc(Nx, Ny))
                 + tpap._l8(L_enc) + tpap._l8(self._R_enc) + tpap._l8(Z_enc) + tpap._l8(V_enc)
                 + tpap._l8(tpap._encode_w(self._w)))
        T = hfn(trans)

        ml = 16 if self._cmac else 32
        conf = tpap._hkdf_expand("ConfirmationKeys", T, ml * 2, self._hkdf_hash)
        KcA, KcB = conf[:ml], conf[ml:ml * 2]
        dlen = 64 if self._hkdf_hash == "SHA512" else 32
        shared = tpap._hkdf_expand("SharedKey", T, dlen, self._hkdf_hash)
        mac_fn = tpap._cmac_aes if self._cmac else (lambda k, d: tpap._hmac_fn(self._hkdf_hash, k, d))

        # A real device rejects a client whose confirmation MAC doesn't match
        # what it derived — surfaced as an error_code, exactly like the
        # pake_register-failure path, rather than a raised exception (an
        # auth failure is a protocol outcome, not a transport error).
        expected_u_conf = mac_fn(KcA, self._R_enc)
        if not _consteq(expected_u_conf, u_conf_client):
            return {"error_code": -1}

        dev_confirm = mac_fn(KcB, L_enc)
        self._cipher_id = self.encryption
        self._key, self._base_nonce = tpap._derive_cipher(shared, self._cipher_id, self._hkdf_hash)

        return {"result": {
            "dev_confirm": tpap._b64e(dev_confirm),
            "sessionId": self.session_id,
            "start_seq": self.start_seq,
        }}

    # ---- encrypted transport ---------------------------------------------------
    def _handle_encrypted(self, path: str, raw: bytes) -> bytes:
        assert path == f"/stok={self.session_id}/ds", path
        seq = struct.unpack(">I", raw[:4])[0]
        plain = tpap._decrypt(self._cipher_id, self._key, self._base_nonce, raw[4:], seq)
        req = json.loads(plain.decode())
        result = self.responses.get(req["method"], {})
        resp = {"error_code": 0, "result": result}
        ct = tpap._encrypt(self._cipher_id, self._key, self._base_nonce,
                            json.dumps(resp).encode(), seq)
        return struct.pack(">I", seq) + ct

    def attach(self, client: "tpap.TapoVacuumClient") -> None:
        """Monkeypatch a TapoVacuumClient to talk to this fake device
        in-process instead of over HTTP."""
        def fake_post(path, body=None, binary=False):
            return self.handle_post(path, body, binary=binary)
        client._post = fake_post


def _consteq(a: bytes, b: bytes) -> bool:
    return len(a) == len(b) and all(x == y for x, y in zip(a, b))
