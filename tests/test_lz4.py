"""Round-trip and hand-crafted-block tests for the pure-Python LZ4 block
decompressor in coordinator.py (`_lz4_block_decompress`), which decodes the
map pixel buffer returned by getMapData. There's no C extension involved,
so a bug here would silently corrupt every rendered map / room lookup."""
from __future__ import annotations

import os

import pytest

from custom_components.tapo_rv30.coordinator import _lz4_block_decompress

from .helpers import encode_lz4_literal_block


@pytest.mark.parametrize(
    "size",
    [0, 1, 5, 14, 15, 16, 255, 256, 300, 510, 511, 512, 765],
)
def test_literal_only_round_trip(size: int) -> None:
    """Literal runs below/at/above the 15-token threshold, including the
    255-continuation-byte boundaries used for long literal lengths."""
    data = os.urandom(size)
    block = encode_lz4_literal_block(data)
    assert _lz4_block_decompress(block, uncompressed_size=size) == data


def test_basic_match_copy() -> None:
    """literal "abc" + a 6-byte match copied from offset 3 -> "abcabcabc".

    Exercises a match whose length exceeds its offset (an overlapping copy,
    where bytes being read were themselves just written earlier in the same
    copy) — the classic LZ4 edge case a naive `out[dst:dst+n] = out[src:src+n]`
    slice copy gets wrong.
    """
    token = bytes([(3 << 4) | 2])  # lit_len=3, match_len=2+4=6
    block = token + b"abc" + bytes([3, 0])  # offset=3 (little-endian)
    assert _lz4_block_decompress(block, uncompressed_size=9) == b"abcabcabc"


def test_non_overlapping_match_copy() -> None:
    """literal "abcdXYZ" + a 4-byte match from offset 7 (non-overlapping)."""
    token = bytes([(7 << 4) | 0])  # lit_len=7, match_len=0+4=4
    block = token + b"abcdXYZ" + bytes([7, 0])
    assert _lz4_block_decompress(block, uncompressed_size=11) == b"abcdXYZabcd"


def test_extended_match_length() -> None:
    """literal "AB" + a 25-byte overlapping match (length >= 19, so the
    match-length nibble maxes out at 15 and continuation bytes are read)."""
    token = bytes([(2 << 4) | 15])  # lit_len=2, match_len nibble maxed (=15)
    block = token + b"AB" + bytes([2, 0]) + bytes([6])  # +6 -> match_len=25
    expected = (b"AB" * 14)[:27]  # 2 literal + 25 matched = 27 bytes
    assert _lz4_block_decompress(block, uncompressed_size=27) == expected


def test_extended_literal_length() -> None:
    """A literal run of exactly 20 bytes (15 + one continuation byte of 5),
    ending the block (no match section, as for a block's final sequence)."""
    data = bytes(range(20))
    token = bytes([0xF0])  # lit_len nibble maxed (=15)
    block = token + bytes([5]) + data  # +5 -> lit_len=20
    assert _lz4_block_decompress(block, uncompressed_size=20) == data
