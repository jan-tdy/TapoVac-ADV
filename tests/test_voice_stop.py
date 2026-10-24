"""Regression coverage for the Assist stop command."""
from __future__ import annotations

import asyncio
import sys
import types

from custom_components.tapo_rv30 import voice
from custom_components.tapo_rv30.const import DOMAIN


def test_voice_stop_stops_and_confirms_without_run_cleanup(monkeypatch) -> None:
    callbacks = []

    class Manager:
        def register_trigger(self, sentences, callback):
            callbacks.append((sentences, callback))
            return lambda: None

    manager = Manager()
    conversation = types.ModuleType("homeassistant.components.conversation")
    conversation.get_agent_manager = lambda hass: manager
    components = types.ModuleType("homeassistant.components")
    components.conversation = conversation
    monkeypatch.setitem(sys.modules, "homeassistant.components", components)
    monkeypatch.setitem(sys.modules, "homeassistant.components.conversation", conversation)
    monkeypatch.setattr(sys.modules["homeassistant"], "components", components, raising=False)

    stopped = []
    refreshed = []

    class Client:
        def stop(self):
            stopped.append(True)

    class Coordinator:
        device_name = "Tapo RV30"
        client = Client()

        async def async_refresh_soon(self):
            refreshed.append(True)

    coordinator = Coordinator()

    async def add_executor_job(fn, *args):
        return fn(*args)

    hass = types.SimpleNamespace(
        data={DOMAIN: {"robot": coordinator}},
        async_add_executor_job=add_executor_job,
    )
    voice.async_setup_voice(hass)
    stop_handler = next(
        cb for sentences, cb in callbacks
        if sentences[:len(voice.SENTENCES_STOP)] == voice.SENTENCES_STOP
    )

    async def run_handler():
        return await stop_handler(types.SimpleNamespace(text="stop vacuum"), None)

    assert asyncio.run(run_handler()) == "Tapo RV30 stopped."
    assert stopped == [True]
    assert refreshed == [True]
