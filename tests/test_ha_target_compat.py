"""Target expansion must work with Home Assistant's current target helper."""
from __future__ import annotations

import sys
import types

from custom_components.tapo_rv30.services import _target_entity_ids


def test_target_entity_ids_uses_new_target_module_when_available(monkeypatch) -> None:
    class _FakeSelectedEntities:
        referenced = {"vacuum.jedalen"}
        indirectly_referenced: set[str] = set()

    class _FakeTargetSelection:
        def __init__(self, data: dict) -> None:
            self.data = data

    fake_target_module = types.ModuleType("homeassistant.helpers.target")
    fake_target_module.TargetSelection = _FakeTargetSelection
    fake_target_module.async_extract_referenced_entity_ids = (
        lambda hass, selection: _FakeSelectedEntities()
    )
    monkeypatch.setitem(sys.modules, "homeassistant.helpers.target", fake_target_module)

    call = types.SimpleNamespace(data={"device_id": "device-id"})
    assert _target_entity_ids(hass=object(), call=call) == ["vacuum.jedalen"]
