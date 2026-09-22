"""Config flow for SkyHub Core."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkyHubAuthError, SkyHubClient, SkyHubError
from .const import CONF_HOST, CONF_TOKEN, CONF_VERIFY_SSL, DOMAIN

STEP_USER = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


def normalise_host(raw: str) -> str:
    """Accept what people actually type and return a usable base URL.

    A bare host or an address with a port is far more likely to be entered
    than a full URL, and SkyHub is served over plain HTTP on the local
    network by default.
    """
    host = raw.strip().rstrip("/")
    if not host:
        raise ValueError("empty host")
    if "://" not in host:
        host = f"http://{host}"
    parsed = urlparse(host)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"not a usable address: {raw}")
    return host


class SkyHubConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                host = normalise_host(user_input[CONF_HOST])
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                verify_ssl = user_input.get(CONF_VERIFY_SSL, True)
                client = SkyHubClient(
                    async_get_clientsession(self.hass, verify_ssl=verify_ssl),
                    host,
                    user_input[CONF_TOKEN],
                    verify_ssl=verify_ssl,
                )
                try:
                    await client.async_get_roof()
                except SkyHubAuthError:
                    errors[CONF_TOKEN] = "invalid_auth"
                except SkyHubError:
                    errors["base"] = "cannot_connect"
                else:
                    # One entry per SkyHub instance. The roof is a single
                    # physical thing; two entries would fight over it.
                    await self.async_set_unique_id(host)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="SkyHub",
                        data={
                            CONF_HOST: host,
                            CONF_TOKEN: user_input[CONF_TOKEN],
                            CONF_VERIFY_SSL: verify_ssl,
                        },
                    )
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace a token that SkyHub no longer accepts.

        Generating a new Home Assistant token in SkyHub revokes the old one,
        so this is the expected path after rotating it — not an error state.
        """
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
            client = SkyHubClient(
                async_get_clientsession(self.hass, verify_ssl=verify_ssl),
                entry.data[CONF_HOST],
                user_input[CONF_TOKEN],
                verify_ssl=verify_ssl,
            )
            try:
                await client.async_get_roof()
            except SkyHubAuthError:
                errors[CONF_TOKEN] = "invalid_auth"
            except SkyHubError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
