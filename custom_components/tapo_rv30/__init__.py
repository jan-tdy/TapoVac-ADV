"""Tapo RV30 Robot Vacuum integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .aes import AesVacuumClient
from .const import CONF_MAC, CONF_POLL_INTERVAL, CONF_SECURITY, CONF_TRANSPORT, DEFAULT_PORT, DOMAIN, FAST_INTERVAL, TRANSPORT_AES

VOICE_KEY = f"{DOMAIN}_voice"
from .tpap import TapoVacuumClient, learned_entry_data

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
    from homeassistant.loader import async_get_integration
    integration = await async_get_integration(hass, DOMAIN)
    if any(e.options.get(OPT_SHOW_PANEL, True) for e in hass.config_entries.async_entries(DOMAIN)):
        await async_setup_panel(hass, integration.version or "0")
    else:
        async_remove_panel_if_present(hass)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from functools import partial
    # Keep this import inside setup: the standalone protocol/coordinator tests
    # stub the Home Assistant modules they need and do not provide loader.
    from .backup_ws import async_setup_backup_ws
    from .coordinator import TapoCoordinator
    from .frontend import async_setup_frontend, async_setup_panel
    from .history_ws import async_setup_history_ws
    from .log_ws import async_setup_log_ws
    from . import logtail
    from .map_edit_ws import async_setup_map_edit_ws
    from .map_restore import async_setup_map_restore
    from .planner import TapoPlanner
    from .planner_ws import async_setup_planner_ws
    from .services import async_resume_zone_restore, async_setup_services
    from .voice import async_setup_voice

    # One ring buffer of this integration's own log records for the whole process, installed
    # once no matter how many robots are configured; the Log tab reads it through log_ws.
    logtail.install()
    await async_setup_frontend(hass)
    # Entries created before transport detection have no CONF_TRANSPORT: TPAP.
    client_cls = AesVacuumClient if entry.data.get(CONF_TRANSPORT) == TRANSPORT_AES else TapoVacuumClient
    client = await hass.async_add_executor_job(partial(
        client_cls,
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        port=DEFAULT_PORT,
        cache_dir=hass.config.path(".storage", "tapo_rv30"),
    ))
    if client_cls is TapoVacuumClient:
        client.expected_security = entry.data.get(CONF_SECURITY)
        client.expected_mac = entry.data.get(CONF_MAC)
    coordinator = TapoCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    if client_cls is TapoVacuumClient:
        learned = learned_entry_data(entry.data, client.security, client.session_mac)
        if learned is not None:
            hass.config_entries.async_update_entry(entry, data=learned)
            client.expected_mac = learned.get(CONF_MAC)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_resume_zone_restore(hass, coordinator)
    # The smart cleaning planner: one instance per robot, wired to the coordinator.
    coordinator.planner = TapoPlanner(hass, coordinator, entry)
    await coordinator.planner.async_load()
    async_setup_planner_ws(hass)
    async_setup_map_edit_ws(hass)
    async_setup_map_restore(hass)
    async_setup_backup_ws(hass)
    async_setup_history_ws(hass)
    async_setup_log_ws(hass)
    coordinator.planner.async_start()
    entry.async_on_unload(coordinator.planner.async_stop)
    # Sidebar page, unless this entry has turned it off (see the options flow).
    from .const import OPT_SHOW_PANEL
    from homeassistant.loader import async_get_integration
    if entry.options.get(OPT_SHOW_PANEL, True):
        integration = await async_get_integration(hass, DOMAIN)
        await async_setup_panel(hass, integration.version or "0")
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    _refresh_voice(hass, async_setup_voice)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .services import async_unload_services, cancel_zone_restore_tasks

    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        cancel_zone_restore_tasks(entry.entry_id)
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None and hasattr(coordinator.client, "close"):
            coordinator.client.close()
        if not hass.data[DOMAIN]:
            async_unload_services(hass)
            from .frontend import async_remove_panel_if_present
            async_remove_panel_if_present(hass)
            if (unregister := hass.data.pop(VOICE_KEY, None)) is not None:
                unregister()
        else:
            from .voice import async_setup_voice
            _refresh_voice(hass, async_setup_voice)
    return ok


def _refresh_voice(hass: HomeAssistant, setup) -> None:
    """Rebuild named voice sentences whenever the configured robot set changes."""
    if (unregister := hass.data.pop(VOICE_KEY, None)) is not None:
        unregister()
    try:
        hass.data[VOICE_KEY] = setup(hass)
    except Exception:
        _LOGGER.exception("Could not register Tapo voice commands")
