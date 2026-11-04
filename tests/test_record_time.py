"""Clean-record timestamps for the Last Clean sensor (pure, no Home Assistant).

Regression for issue #137: an out-of-range record timestamp made datetime.fromtimestamp
raise OSError inside the entity's state property, so Home Assistant could not write the
state on any refresh. record_time() must return None instead of raising.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest

from custom_components.tapo_rv30 import mapdata


def test_valid_unix_seconds_become_aware_utc():
    assert mapdata.record_time(1_700_000_000) == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_string_and_float_timestamps_are_accepted():
    assert mapdata.record_time("1700000000") == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert mapdata.record_time(1_700_000_000.0) == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


@pytest.mark.parametrize("bad", [
    2 ** 40,             # beyond 32-bit time_t on 32-bit platforms, beyond datetime's year 9999 range
    10 ** 30,            # far outside any platform range
    1.7e12,              # milliseconds passed where seconds are expected
    float("inf"),
    float("nan"),
    "not a number",
    [1700000000],        # unhashable, wrong type
])
def test_unconvertible_values_return_none_without_raising(bad):
    assert mapdata.record_time(bad) is None


def test_none_is_none_and_is_not_logged(caplog):
    with caplog.at_level(logging.WARNING, logger=mapdata.__name__):
        assert mapdata.record_time(None) is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_bad_value_is_logged_once(caplog):
    mapdata._BAD_RECORD_TIMES.discard(repr(10 ** 30))
    with caplog.at_level(logging.WARNING, logger=mapdata.__name__):
        for _ in range(3):
            assert mapdata.record_time(10 ** 30) is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert str(10 ** 30) in warnings[0].getMessage()
