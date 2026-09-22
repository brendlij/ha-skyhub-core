"""The SkyHub Core integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkyHubClient
from .const import CONF_HOST, CONF_TOKEN, CONF_VERIFY_SSL, DOMAIN, STATIC_URL
from .coordinator import SkyHubCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.SENSOR,
]

type SkyHubConfigEntry = ConfigEntry[SkyHubCoordinator]


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the 3D roof card and its models from Home Assistant itself.

    The iframe this replaces pointed at SkyHub directly, so a dashboard
    opened from outside the network went blank: the browser could reach
    Home Assistant but not the Pi. Serving the viewer here removes that
    split — the card is a dashboard resource like any other, and the roof's
    position comes from an entity rather than a call of its own.

    Registered once per Home Assistant run, not per config entry.
    """
    if hass.data.get(f"{DOMAIN}_frontend"):
        return
    hass.data[f"{DOMAIN}_frontend"] = True

    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(www), cache_headers=True)]
    )
    # add_extra_js_url rather than a Lovelace resource entry: it works in
    # both storage and YAML dashboard modes, and leaves nothing behind in
    # the user's resource list if the integration is removed.
    add_extra_js_url(hass, f"{STATIC_URL}/skyhub-roof-card.js")
    _LOGGER.debug("Registered the roof card at %s", STATIC_URL)


async def async_setup_entry(hass: HomeAssistant, entry: SkyHubConfigEntry) -> bool:
    await _async_register_frontend(hass)
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    client = SkyHubClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        entry.data[CONF_HOST],
        entry.data[CONF_TOKEN],
        verify_ssl=verify_ssl,
    )
    coordinator = SkyHubCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_stream()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SkyHubConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: SkyHubConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
