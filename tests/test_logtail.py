"""The sidebar page's Log tab: a bounded ring buffer attached to this integration's logger
namespace (pure, no Home Assistant)."""
from __future__ import annotations

import logging

from custom_components.tapo_rv30 import logtail


def _fresh_logger(name: str = "custom_components.tapo_rv30._test") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    return logger


def test_handler_keeps_newest_first_and_bounded():
    handler = logtail.RingBufferHandler(capacity=3)
    logger = _fresh_logger()
    logger.addHandler(handler)
    for i in range(5):
        logger.warning("msg %d", i)
    records = handler.list()
    assert len(records) == 3
    assert [r["message"] for r in records] == ["msg 4", "msg 3", "msg 2"]
    assert all(r["level"] == "WARNING" for r in records)
    logger.removeHandler(handler)


def test_handler_records_level_and_logger_name():
    handler = logtail.RingBufferHandler(capacity=10)
    logger = _fresh_logger("custom_components.tapo_rv30.tpap")
    logger.addHandler(handler)
    logger.error("boom")
    logger.info("fine")
    records = handler.list()
    assert records[0]["level"] == "INFO" and records[1]["level"] == "ERROR"
    assert all(r["logger"] == "custom_components.tapo_rv30.tpap" for r in records)
    logger.removeHandler(handler)


def test_list_respects_limit():
    handler = logtail.RingBufferHandler(capacity=10)
    logger = _fresh_logger()
    logger.addHandler(handler)
    for i in range(5):
        logger.debug("m%d", i)
    assert len(handler.list(limit=2)) == 2
    assert len(handler.list()) == 5
    logger.removeHandler(handler)


def test_clear_empties_the_buffer():
    handler = logtail.RingBufferHandler(capacity=10)
    logger = _fresh_logger()
    logger.addHandler(handler)
    logger.warning("one")
    assert len(handler) == 1
    handler.clear()
    assert len(handler) == 0
    assert handler.list() == []
    logger.removeHandler(handler)


def test_install_is_idempotent_and_reuses_the_same_handler():
    logging.getLogger(logtail.LOGGER_NAME).handlers.clear()
    try:
        first = logtail.install(capacity=7)
        second = logtail.install(capacity=99)   # capacity is only used on first install
        assert first is second
        assert first.capacity == 7
    finally:
        logtail.uninstall(first)


def test_human_time_is_a_plain_local_timestamp():
    text = logtail.human_time(0)
    assert len(text) == 19 and text[4] == "-" and text[13] == ":"
