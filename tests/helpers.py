"""Shared test helpers."""
from __future__ import annotations


def encode_lz4_literal_block(data: bytes) -> bytes:
    """Encode `data` as a single-sequence LZ4 block containing only a
    literal run (no match) — a minimal, always-valid LZ4 block producer used
    to build round-trip fixtures for `_lz4_block_decompress`, which only ever
    needs to *decode* real device data, not produce it.
    """
    n = len(data)
    if n < 15:
        token = bytes([n << 4])
        return token + data
    token = bytes([0xF0])
    rem = n - 15
    extra = bytearray()
    while rem >= 255:
        extra.append(255)
        rem -= 255
    extra.append(rem)
    return token + bytes(extra) + data
