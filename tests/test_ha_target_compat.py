"""Regression test for the HA 2026.10 breaking change that removed
`async_extract_referenced_entity_ids` from `homeassistant.helpers.service`
outright (no compatibility shim on HA's side), which made importing
`custom_components/tapo_rv30/__init__.py` fail at startup and took down the
entire integration — not just the two services.

The replacement lives in `homeassistant.helpers.target` and takes a
`TargetSelection(call.data)` instead of the raw `ServiceCall`. `__init__.py`
tries that new module first and falls back to the old `helpers.service`
import (exercised implicitly by every other test via the stub in
conftest.py, which only defines the old location) for older HA installs.
This test forces the new module to exist so the *other* branch of that
try/except also gets covered.
"""
from __future__ import annotations

import importlib
import sys
import types


def test_target_entity_ids_uses_new_target_module_when_available(monkeypatch) -> None:
    class _FakeSelectedEntities:
        def __init__(self, referenced: set[str]) -> None:
            self.referenced = referenced
            self.indirectly_referenced: set[str] = set()

    class _FakeTargetSelection:
        def __init__(self, data: dict) -> None:
            self.data = data

    def _fake_async_extract_referenced_entity_ids(hass, target_selection, expand_group=True):
        return _FakeSelectedEntities(set(target_selection.data.get("entity_id", [])))

    fake_target_module = types.ModuleType("homeassistant.helpers.target")
    fake_target_module.TargetSelection = _FakeTargetSelection
    fake_target_module.async_extract_referenced_entity_ids = (
        _fake_async_extract_referenced_entity_ids
    )
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.target", fake_target_module)

    # Re-execute __init__.py's module-level try/except against the now-
    # present homeassistant.helpers.target, instead of the cached module
    # (already imported by earlier tests) that took the legacy branch.
    monkeypatch.delitem(sys.modules, "custom_components.tapo_rv30", raising=False)
    tapo_rv30 = importlib.import_module("custom_components.tapo_rv30")

    call = types.SimpleNamespace(data={"entity_id": ["vacuum.jedalen"]})
    assert tapo_rv30._target_entity_ids(hass=object(), call=call) == ["vacuum.jedalen"]
