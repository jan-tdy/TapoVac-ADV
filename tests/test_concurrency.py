"""Regression coverage for issue #45: TapoVacuumClient's session/sequence
state (self._seq, self._key, self._base_nonce, self._session_id, ...) must be
serialized across threads. Home Assistant runs every `send()` call (from the
coordinator's poll loop and from entity actions/services alike) via
`hass.async_add_executor_job`, which is *not* serialized per client instance —
so two threads can otherwise race inside `send()`'s read-modify-write of
`self._seq`, reusing an AEAD nonce, or have one thread's re-auth
(`_clear_session()` + `authenticate()`) corrupt session state out from under
another thread's in-flight request.

This drives many concurrent `send()` calls (with an injected delay inside the
"device" response handling to force interleaving that would otherwise be rare
under the GIL) and asserts every request used a distinct sequence number and
succeeded — which requires `send()` to hold a lock for the read of `self._seq`,
the encrypt/post/decrypt round trip, and the increment, as one atomic unit.
"""
from __future__ import annotations

import threading
import time

from .fake_device import FakeDevice
from .test_handshake import _make_client


def test_concurrent_send_calls_do_not_reuse_sequence_numbers(tmp_path) -> None:
    device = FakeDevice(
        username="admin", password="hunter2",
        responses={"getVacStatus": {"status": 1, "err_status": [0]}},
    )
    client = _make_client(tmp_path)
    device.attach(client)
    client.authenticate()

    seen_seqs: list[int] = []
    seq_lock = threading.Lock()

    real_handle_encrypted = device._handle_encrypted

    def delayed_handle_encrypted(path, raw):
        # Widen the race window a missing lock would otherwise need luck to
        # hit: read the client's current sequence number *before* the fake
        # device processes the request, sleep to force a context switch, then
        # process. Without TapoVacuumClient's lock, a second thread's send()
        # would read the same self._seq during this window.
        with seq_lock:
            seen_seqs.append(client._seq)
        time.sleep(0.005)
        return real_handle_encrypted(path, raw)

    device._handle_encrypted = delayed_handle_encrypted

    errors: list[Exception] = []

    def worker() -> None:
        try:
            resp = client.send("getVacStatus")
            assert resp["result"]["status"] == 1
        except Exception as exc:  # noqa: BLE001 - surfaced via `errors`
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"send() raised under concurrency: {errors}"
    assert len(seen_seqs) == len(set(seen_seqs)), (
        f"a sequence number (and therefore nonce) was reused across "
        f"concurrent send() calls: {seen_seqs}"
    )
    assert device.call_counts["getVacStatus"] == 20
