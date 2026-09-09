"""Config flow for Tapo RV30."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DEFAULT_PORT, DOMAIN
from .tpap import AuthError, TapoVacuumClient

STEP_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_USERNAME, default=""): str,
    vol.Required(CONF_PASSWORD, default=""): str,
})


async def _test_connection(hass: HomeAssistant, host: str, user: str, pw: str) -> str | None:
    """Return None on success, error key string on failure."""
    def _try():
        c = TapoVacuumClient(host, user, pw, DEFAULT_PORT,
                              cache_dir=hass.config.path(".storage", DOMAIN))
        c.authenticate()
    try:
        await hass.async_add_executor_job(_try)
        return None
    except AuthError:
        return "invalid_auth"
    except Exception:
        return "cannot_connect"


class TapoRV30ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            user = user_input[CONF_USERNAME].strip()
            pw   = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            err = await _test_connection(self.hass, host, user, pw)
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=f"Tapo RV30 ({host})",
                    data={CONF_HOST: host, CONF_USERNAME: user, CONF_PASSWORD: pw},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Update an existing entry's host/credentials in place.

        Lets a changed vacuum IP (common on DHCP with no static
        reservation) or TP-Link password be fixed without removing and
        re-adding the integration, which would discard the entry's
        unique_id-based identity along with any customized entity
        names/IDs, area assignments, and segment-to-area mapping (#38).
        """
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            user = user_input[CONF_USERNAME].strip()
            pw   = user_input[CONF_PASSWORD] or reconfigure_entry.data[CONF_PASSWORD]

            # A different entry already using this host is still a conflict;
            # the entry being reconfigured is excluded from that check.
            conflict = any(
                entry.entry_id != reconfigure_entry.entry_id and entry.unique_id == host
                for entry in self._async_current_entries()
            )
            if conflict:
                errors["base"] = "already_configured"
            else:
                err = await _test_connection(self.hass, host, user, pw)
                if err:
                    errors["base"] = err
                else:
                    await self.async_set_unique_id(host)
                    return self.async_update_reload_and_abort(
                        reconfigure_entry,
                        data={CONF_HOST: host, CONF_USERNAME: user, CONF_PASSWORD: pw},
                    )

        return self.async_show_form(
            step_id="reconfigure",
            # Pre-fill host/username from the entry; leave password blank
            # rather than echoing the stored one back into the form.
            data_schema=self.add_suggested_values_to_schema(
                STEP_SCHEMA,
                {
                    CONF_HOST: reconfigure_entry.data[CONF_HOST],
                    CONF_USERNAME: reconfigure_entry.data[CONF_USERNAME],
                },
            ),
            errors=errors,
        )
