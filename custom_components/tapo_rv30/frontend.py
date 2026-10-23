"""Serve static robot icons, rendered last-clean map images and the planner page."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

STATIC_URL = f"/{DOMAIN}_static"
DATA_FRONTEND = f"{DOMAIN}_frontend_ready"
PANEL_FILE = "tapo-planner-panel.js"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Idempotently register the robot icons and authenticated image endpoint."""
    if hass.data.get(DATA_FRONTEND):
        return
    hass.data[DATA_FRONTEND] = True

    await hass.http.async_register_static_paths([
        StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "frontend"), cache_headers=False)
    ])
    hass.http.register_view(LastCleanView())


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


