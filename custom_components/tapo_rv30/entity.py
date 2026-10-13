"""Shared base for every Tapo RV30 entity — one Home Assistant device per
config entry, described from data the coordinator fetches once at startup
(coordinator.device_name / device_model) instead of a literal model string
duplicated into every entity class (see issue #36)."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TapoCoordinator

_LOGGER = logging.getLogger(__name__)


class TapoEntity(CoordinatorEntity[TapoCoordinator]):
    """Mixin providing device_info for every Tapo RV30 entity.

    Combine with the platform's own entity base, e.g.
    `class Foo(TapoEntity, SensorEntity)`. Platforms whose base class needs
    its own explicit `__init__` call (e.g. Camera) can call
    `TapoEntity.__init__(self, coordinator, entry)` directly instead of
    relying on cooperative `super()` — see camera.py.
    """

    def __init__(self, coordinator: TapoCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def device_info(self):
        return {
            "identifiers":  {(DOMAIN, self._entry.entry_id)},
            "name":         self.coordinator.device_name,
            "manufacturer": "TP-Link",
            "model":        self.coordinator.device_model,
        }

    async def _async_client_call(self, description: str, func, *args):
        # Shared by every platform's action methods so a raw device error
        # (e.g. RuntimeError("Device error -X")) or transport failure is
        # turned into a HomeAssistantError the caller's action
        # popup/response actually shows, instead of an unhandled exception
        # HA can only log as "Unexpected exception" (issue #50).
        try:
            return await self.hass.async_add_executor_job(func, *args)
        except Exception as exc:
            _LOGGER.warning("%s failed: %s", description, exc)
            raise HomeAssistantError(f"{description} failed: {exc}") from exc

    async def _async_run_client_job(self, description: str, func, *args) -> None:
        # Like _async_client_call, but also requests a coordinator refresh
        # afterwards — for actions that mutate device state.
        await self._async_client_call(description, func, *args)
        await self.coordinator.async_request_refresh()
