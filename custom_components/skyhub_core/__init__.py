"""The SkyHub Core integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkyHubClient
from .const import CONF_HOST, CONF_TOKEN, CONF_VERIFY_SSL, DOMAIN
from .coordinator import SkyHubCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.SENSOR,
]

type SkyHubConfigEntry = ConfigEntry[SkyHubCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SkyHubConfigEntry) -> bool:
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
