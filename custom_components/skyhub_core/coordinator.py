"""Keeps one roof's state current, by stream where possible."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SkyHubAuthError, SkyHubClient, SkyHubError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MOVING_SCAN_INTERVAL,
    REQUEST_REFRESH_COOLDOWN,
    STREAM_RETRY_SECONDS,
)
from .model import RoofState, parse_roof

_LOGGER = logging.getLogger(__name__)


class SkyHubCoordinator(DataUpdateCoordinator[RoofState]):
    """Polls the roof, and refreshes immediately on a streamed event.

    The poll interval is the floor, not the resolution. A roof that starts
    moving — above all one the controller closes by itself because of rain —
    shows up in Home Assistant within the round trip of one read, not on the
    next tick.
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: SkyHubClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
            config_entry=entry,
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_COOLDOWN,
                immediate=True,
            ),
        )
        self.client = client
        self._stream_task: asyncio.Task | None = None
        self._stream_connected = False

    @property
    def stream_connected(self) -> bool:
        """Whether updates are arriving by push rather than only by poll."""
        return self._stream_connected

    async def _async_update_data(self) -> RoofState:
        try:
            roof = parse_roof(await self.client.async_get_roof())
        except SkyHubAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SkyHubError as err:
            raise UpdateFailed(str(err)) from err
        self._retune_interval(roof)
        return roof

    def _retune_interval(self, roof: RoofState) -> None:
        """Poll quickly while the roof moves, slowly while it sits still.

        A roof spends nearly all its time parked, where a half-minute tick
        is plenty. During the minute or two it travels — or while the
        controller is closing it on its own — the position changes the whole
        time, and a stale number is exactly what someone is watching for.
        """
        moving = roof.is_opening or roof.is_closing or roof.rain_closure_active
        wanted = MOVING_SCAN_INTERVAL if moving else DEFAULT_SCAN_INTERVAL
        if self.update_interval != wanted:
            self.update_interval = wanted

    def start_stream(self) -> None:
        if self._stream_task is None or self._stream_task.done():
            self._stream_task = self.config_entry.async_create_background_task(
                self.hass, self._stream(), f"{DOMAIN}_events"
            )

    async def async_shutdown(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        await super().async_shutdown()

    async def _stream(self) -> None:
        """Follow the event stream, reconnecting until the entry unloads.

        A dropped stream is not an error worth surfacing: polling keeps the
        integration correct on its own, just less promptly. It is logged
        once at warning level and then at debug, so a flaky network does not
        fill the log.
        """
        warned = False
        while True:
            try:
                async for _ in self.client.async_events():
                    self._stream_connected = True
                    warned = False
                    await self.async_request_refresh()
                # A clean end of stream still means we are no longer pushed.
                self._stream_connected = False
            except asyncio.CancelledError:
                self._stream_connected = False
                raise
            except SkyHubAuthError:
                self._stream_connected = False
                _LOGGER.debug("Event stream rejected the token; polling continues")
                return
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                self._stream_connected = False
                if warned:
                    _LOGGER.debug("SkyHub event stream retrying: %s", err)
                else:
                    _LOGGER.warning(
                        "SkyHub event stream lost, falling back to polling: %s", err
                    )
                    warned = True
            await asyncio.sleep(STREAM_RETRY_SECONDS)
