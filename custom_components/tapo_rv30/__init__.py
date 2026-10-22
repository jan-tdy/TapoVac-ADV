"""Tapo RV30 Robot Vacuum integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .aes import AesVacuumClient
from .const import CONF_POLL_INTERVAL, CONF_TRANSPORT, DEFAULT_PORT, DOMAIN, FAST_INTERVAL, TRANSPORT_AES

VOICE_KEY = f"{DOMAIN}_voice"
from .tpap import TapoVacuumClient

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.CAMERA, Platform.IMAGE,
             Platform.SELECT, Platform.BUTTON, Platform.SWITCH, Platform.TIME, Platform.NUMBER,
             Platform.UPDATE]


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options live; the map look is re-read on the next render."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return
    await coordinator.async_set_poll_interval(int(entry.options.get(CONF_POLL_INTERVAL, FAST_INTERVAL)))
    # The sidebar planner page: shown unless every entry has turned it off.
    from .frontend import async_remove_panel_if_present, async_setup_panel
    from .const import OPT_SHOW_PANEL
    from homeassistant.helpers.loader import async_get_integration
    integration = await async_get_integration(hass, DOMAIN)
    if any(e.options.get(OPT_SHOW_PANEL, True) for e in hass.config_entries.async_entries(DOMAIN)):
        await async_setup_panel(hass, integration.version or "0")
    else:
        async_remove_panel_if_present(hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Keep this import inside setup: the standalone protocol/coordinator tests
    # stub the Home Assistant modules they need and do not provide loader.
    from .coordinator import TapoCoordinator
    from .frontend import async_setup_frontend, async_setup_panel
    from .planner import TapoPlanner
    from .planner_ws import async_setup_planner_ws
    from .services import async_setup_services
    from .voice import async_setup_voice

    await async_setup_frontend(hass)
    # Entries created before transport detection have no CONF_TRANSPORT: TPAP.
    client_cls = AesVacuumClient if entry.data.get(CONF_TRANSPORT) == TRANSPORT_AES else TapoVacuumClient
    client = client_cls(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=DEFAULT_PORT,
        cache_dir=hass.config.path(".storage", "tapo_rv30"),
    )
    coordinator = TapoCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    # The smart cleaning planner: one instance per robot, wired to the coordinator.
    coordinator.planner = TapoPlanner(hass, coordinator, entry)
    await coordinator.planner.async_load()
    async_setup_planner_ws(hass)
    coordinator.planner.async_start()
    entry.async_on_unload(coordinator.planner.async_stop)
    # Sidebar page, unless this entry has turned it off (see the options flow).
    from .const import OPT_SHOW_PANEL
    from homeassistant.helpers.loader import async_get_integration
    if entry.options.get(OPT_SHOW_PANEL, True):
        integration = await async_get_integration(hass, DOMAIN)
        await async_setup_panel(hass, integration.version or "0")
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    if VOICE_KEY not in hass.data:
        hass.data[VOICE_KEY] = async_setup_voice(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .services import async_unload_services

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None and hasattr(coordinator.client, "close"):
            coordinator.client.close()
        if not hass.data[DOMAIN]:
            async_unload_services(hass)
            from .frontend import async_remove_panel_if_present
            async_remove_panel_if_present(hass)
            if (unregister := hass.data.pop(VOICE_KEY, None)) is not None:
                unregister()
    return ok
