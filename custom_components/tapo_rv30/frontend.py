"""Serve static robot icons, rendered last-clean map images and the planner page."""
from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .maprender import _png, render_record

STATIC_URL = f"/{DOMAIN}_static"
DATA_FRONTEND = f"{DOMAIN}_frontend_ready"
PANEL_FILE = "tapo-planner-panel.js"
_LOGGER = logging.getLogger(__name__)


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Idempotently register the robot icons and authenticated image endpoint."""
    if hass.data.get(DATA_FRONTEND):
        return
    hass.data[DATA_FRONTEND] = True

    await hass.http.async_register_static_paths([
        StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)
    ])
    hass.http.register_view(LastCleanView())
    hass.http.register_view(CleanRecordMapView())


class LastCleanView(HomeAssistantView):
    """GET /api/tapo_rv30/<entry_id>/last_clean.png -> the newest run's map."""
    url = f"/api/{DOMAIN}/{{entry_id}}/last_clean.png"
    name = f"api:{DOMAIN}:last_clean"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str) -> web.Response:
        coordinator = request.app["hass"].data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None or not coordinator.last_clean_image_bytes:
            return web.Response(status=404, text="no record")
        return web.Response(body=coordinator.last_clean_image_bytes, content_type="image/png",
                            headers={"Cache-Control": "no-cache"})


class CleanRecordMapView(HomeAssistantView):
    """Render one historical clean on demand, without storing map images in HA."""
    url = f"/api/{DOMAIN}/{{entity_id}}/clean/{{record_index}}"
    name = f"api:{DOMAIN}:clean_record_map"
    requires_auth = True

    async def get(self, request: web.Request, entity_id: str, record_index: str) -> web.Response:
        try:
            index = int(record_index)
            if not 0 <= index <= 1_000_000:
                raise ValueError
        except (TypeError, ValueError):
            return web.Response(status=400, text="invalid record index")
        registry_entry = er.async_get(request.app["hass"]).async_get(entity_id)
        if registry_entry is None or registry_entry.platform != DOMAIN:
            return web.Response(status=404, text="vacuum not found")
        coordinator = request.app["hass"].data.get(DOMAIN, {}).get(registry_entry.config_entry_id)
        if coordinator is None:
            return web.Response(status=404, text="vacuum unavailable")
        try:
            def render() -> bytes:
                detail = coordinator.client.get_clean_record_detail(index)
                return _png(render_record(detail))
            image = await request.app["hass"].async_add_executor_job(render)
        except Exception as exc:
            _LOGGER.debug("Could not render clean map %s for %s: %s", index, entity_id, exc)
            return web.Response(status=404, text="clean map unavailable")
        return web.Response(body=image, content_type="image/png",
                            headers={"Cache-Control": "no-store"})


async def async_setup_panel(hass: HomeAssistant, version: str) -> None:
    """The planner sidebar page: due rooms, conditions, the decision log."""
    from homeassistant.components import panel_custom
    from homeassistant.components.frontend import async_remove_panel

    from .const import PANEL_URL_PATH
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name="tapo-planner-panel",
        sidebar_title="Vacuum",
        sidebar_icon="mdi:robot-vacuum",
        module_url=f"{STATIC_URL}/{PANEL_FILE}?v={version}",
        embed_iframe=False,
        trust_external=False,
        require_admin=False,
    )


@callback
def async_remove_panel_if_present(hass: HomeAssistant) -> None:
    from homeassistant.components.frontend import async_remove_panel

    from .const import PANEL_URL_PATH
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


