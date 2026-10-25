"""Small pure helpers for copying a map: a fresh map id, and the robot's own limit on how
many maps it holds.

Ported from upstream tapo-rv30-ha's mapcopy.py (its only genuinely new module for map
management; everything else upstream added for maps extended existing files). This fork's
restore pipeline differs from upstream's (no "carrier" map is needed for a copy, since the
fresh id never collides with one already on the robot), so only the id-generation piece is
carried over; see mapbackup.reid_bkmap for the matching backup rewrite.
"""
from __future__ import annotations

MAX_MAPS = 3            # the firmware's MAX_SAVE_MAP_NUM


def new_map_id(existing, now: float) -> int:
    """A fresh map id: the robot's own ids are unix timestamps, so use the time, stepping past
    any id already on the robot. Always 10 digits (until 2286) and inside int32 (until 2038)."""
    taken = {int(i) for i in existing}
    mid = int(now)
    while mid in taken:
        mid += 1
    if not 10**9 <= mid < 2**31:
        raise ValueError(f"cannot make a map id from time {now}")
    return mid
