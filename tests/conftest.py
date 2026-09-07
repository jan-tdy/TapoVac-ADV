"""Test setup shared by the whole suite.

The integration lives under ``custom_components/tapo_rv30`` and its package
``__init__.py`` (plus ``coordinator.py``) import real Home Assistant modules
that aren't installed here — this suite targets the protocol/crypto/decoding
logic in ``tpap.py`` and ``coordinator.py``, not Home Assistant's runtime, so
we stand in minimal stand-ins for the handful of HA symbols those modules
import at module load time. This keeps the suite fast and dependency-light
instead of requiring a full Home Assistant install.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# Make `custom_components.tapo_rv30` importable regardless of the cwd pytest
# was invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _module(name: str) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return  # real Home Assistant is installed — use it.

    ha = _module("homeassistant")
    ha_config_entries = _module("homeassistant.config_entries")
    ha_const = _module("homeassistant.const")
    ha_core = _module("homeassistant.core")
    ha_helpers = _module("homeassistant.helpers")
    ha_update_coordinator = _module("homeassistant.helpers.update_coordinator")

    class ConfigEntry:  # noqa: D401 - minimal stand-in
        data: dict = {}

    class Platform:
        VACUUM = "vacuum"
        SENSOR = "sensor"
        CAMERA = "camera"
        SELECT = "select"
        BINARY_SENSOR = "binary_sensor"

    class HomeAssistant:
        ...

    class ServiceCall:
        ...

    class DataUpdateCoordinator:
        def __init__(self, hass, logger, *, name=None, update_interval=None):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval

    class UpdateFailed(Exception):
        ...

    ha_config_entries.ConfigEntry = ConfigEntry
    ha_const.CONF_HOST = "host"
    ha_const.CONF_USERNAME = "username"
    ha_const.CONF_PASSWORD = "password"
    ha_const.Platform = Platform
    ha_core.HomeAssistant = HomeAssistant
    ha_core.ServiceCall = ServiceCall
    ha_update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    ha_update_coordinator.UpdateFailed = UpdateFailed

    ha.config_entries = ha_config_entries
    ha.const = ha_const
    ha.core = ha_core
    ha.helpers = ha_helpers
    ha_helpers.update_coordinator = ha_update_coordinator


_install_homeassistant_stubs()
