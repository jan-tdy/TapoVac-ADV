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


def test_each_distinct_bad_value_is_logged_once(caplog):
    for value in (10 ** 30, 2 ** 40):
        mapdata._BAD_RECORD_TIMES.discard(repr(value))
    with caplog.at_level(logging.WARNING, logger=mapdata.__name__):
        for value in (10 ** 30, 2 ** 40):
            for _ in range(3):
                assert mapdata.record_time(value) is None
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(messages) == 2
    assert str(10 ** 30) in messages[0]
    assert str(2 ** 40) in messages[1]


def test_bad_value_cache_stays_bounded():
    mapdata._BAD_RECORD_TIMES.clear()
    for i in range(1000):
        assert mapdata.record_time(2 ** 40 + i) is None
    assert len(mapdata._BAD_RECORD_TIMES) <= mapdata._BAD_RECORD_TIMES_MAX


def test_empty_string_and_list_timestamps_are_unknown_not_raised():
    assert mapdata.record_time("") is None
    assert mapdata.record_time([]) is None


def test_can_show_as_time_agrees_with_record_time_but_never_logs(caplog):
    with caplog.at_level(logging.WARNING, logger=mapdata.__name__):
        assert mapdata.can_show_as_time(1_700_000_000) is True
        assert mapdata.can_show_as_time(10 ** 30) is False
        assert mapdata.can_show_as_time(None) is False
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_pick_last_record_skips_a_corrupted_timestamp_for_an_older_usable_one():
    # Issue #137 follow-up: a record with a huge/corrupted timestamp always wins a
    # raw-value max(), so it would permanently hide a real, convertible last-clean
    # date behind it instead of just going unknown for that one record.
    records = [
        {"timestamp": 1_700_000_000, "clean_area": 12},
        {"timestamp": 360569737228713984, "clean_area": 99},
    ]
    assert mapdata.pick_last_record(records) == {"timestamp": 1_700_000_000, "clean_area": 12}


def test_pick_last_record_returns_newest_usable_regardless_of_order():
    older = {"timestamp": 1_700_000_000, "clean_area": 12}
    newer = {"timestamp": 1_700_086_400, "clean_area": 7}
    assert mapdata.pick_last_record([older, newer]) == newer
    assert mapdata.pick_last_record([newer, older]) == newer


def test_pick_last_record_does_not_let_a_zero_placeholder_mask_a_corrupted_one():
    # A 0 timestamp means "no record" (see sensor._last_clean_time), not a real
    # clean, so can_show_as_time(0) being True must not let it win "usable" over -
    # and so silently swallow the warning for - an actually corrupted record.
    records = [
        {"timestamp": 0, "clean_area": 0},
        {"timestamp": 360569737228713984, "clean_area": 99},
    ]
    assert mapdata.pick_last_record(records) == {"timestamp": 360569737228713984, "clean_area": 99}


def test_pick_last_record_falls_back_to_raw_max_when_nothing_is_usable():
    records = [
        {"timestamp": 10 ** 30, "clean_area": 1},
        {"timestamp": 10 ** 31, "clean_area": 2},
    ]
    assert mapdata.pick_last_record(records) == {"timestamp": 10 ** 31, "clean_area": 2}


def test_pick_last_record_handles_empty_or_missing_list():
    assert mapdata.pick_last_record([]) == {}
    assert mapdata.pick_last_record(None) == {}
