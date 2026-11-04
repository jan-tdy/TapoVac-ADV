"""Regression for issue #137 follow-up: a record with a null timestamp must not make the
coordinator's newest-record selection raise TypeError (None vs int comparison)."""
from __future__ import annotations

import asyncio

from custom_components.tapo_rv30.coordinator import TapoCoordinator


class _Hass:
    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


class _Client:
    def __init__(self, raw):
        self._raw = raw

    def get_clean_records(self):
        return self._raw


def _fetch(raw):
    coordinator = TapoCoordinator(_Hass(), client=_Client(raw))
    return asyncio.run(coordinator._fetch_new_record())


def test_null_timestamp_beside_a_valid_one_does_not_raise():
    rec = _fetch({"record_list": [{"timestamp": None}, {"timestamp": 1_700_000_000, "clean_time": 5}]})
    assert rec is not None and rec["started"] == 1_700_000_000


def test_only_null_timestamps_returns_no_record_without_raising():
    assert _fetch({"record_list": [{"timestamp": None}, {"timestamp": None}]}) is None
