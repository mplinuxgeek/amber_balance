from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_NAME,
    CONF_SITE_ID,
    CONF_SITE_IDS,
    CONF_SUBSCRIPTION,
    CONF_SURCHARGE_CENTS,
    CONF_TOKEN,
    DEFAULT_NAME,
    DEFAULT_SUBSCRIPTION,
    DEFAULT_SURCHARGE_CENTS,
    DOMAIN,
)
from .sensor import AmberApi


async def _discover_sites(hass: HomeAssistant, token: str) -> list[str]:
    session = async_get_clientsession(hass)
    return await AmberApi.discover_sites(session, token)


class AmberBalanceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}
        if user_input is not None:
            try:
                site_ids = await _discover_sites(self.hass, user_input[CONF_TOKEN])
                if not site_ids:
                    errors["base"] = "no_site"
                else:
                    user_input[CONF_SITE_IDS] = site_ids
                    user_input[CONF_SITE_ID] = site_ids[0]
            except Exception:
                errors["base"] = "auth"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_NAME, data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): str,
                vol.Optional(CONF_SITE_ID): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(
                    CONF_SURCHARGE_CENTS, default=DEFAULT_SURCHARGE_CENTS
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_SUBSCRIPTION, default=DEFAULT_SUBSCRIPTION
                ): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
