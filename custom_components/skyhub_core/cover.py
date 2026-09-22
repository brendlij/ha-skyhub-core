"""The observatory roof as a cover."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkyHubConfigEntry
from .api import SkyHubError
from .entity import SkyHubEntity
from .model import position_command


async def async_setup_entry(
    hass: HomeAssistant, entry: SkyHubConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([SkyHubRoof(entry.runtime_data)])


class SkyHubRoof(SkyHubEntity, CoverEntity):
    """Open, close, stop, or drive the roof to a position."""

    _attr_name = None  # the device is the roof; no sub-name
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "roof")

    @property
    def is_closed(self) -> bool | None:
        return self.roof.is_closed

    @property
    def is_opening(self) -> bool:
        return self.roof.is_opening

    @property
    def is_closing(self) -> bool:
        return self.roof.is_closing

    @property
    def current_cover_position(self) -> int | None:
        """0 is closed and 100 is fully open, the same way SkyHub counts.

        A stale calibration still yields a position. Dropping it would make
        the cover lose its place entirely; position_stale marks it instead,
        so an automation can decide whether to trust the number.
        """
        return self.roof.position

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        roof = self.roof
        attributes: dict[str, Any] = {
            "position_stale": roof.position_stale,
            "hard_stop": roof.hard_stop,
            "close_allowed": roof.close_allowed,
            "rain_auto_close": roof.rain_auto,
            "driver": roof.driver,
            "stream_connected": self.coordinator.stream_connected,
        }
        if roof.reports_diagnostics:
            # Ground truth behind the percentage, plus where the controller
            # thinks it is. Attributes rather than entities: useful when
            # something is wrong, noise on the device page otherwise.
            attributes.update(
                {
                    "mode": roof.mode,
                    "motion": roof.motion,
                    "zone": roof.zone,
                    "homed": roof.homed,
                    "limit_open": roof.limit_open,
                    "limit_close": roof.limit_close,
                    "firmware": roof.fw_version,
                }
            )
        if roof.fault:
            attributes["fault"] = roof.fault
        if roof.close_phase:
            attributes["close_phase"] = roof.close_phase
            attributes["close_reason"] = roof.close_reason
            attributes["close_block"] = roof.close_block
            attributes["close_id"] = roof.close_id
        return attributes

    async def _async_send(self, command: str) -> None:
        try:
            await self.coordinator.client.async_command(command)
        except SkyHubError as err:
            # Surfaces the controller's own reason — rain_lockout,
            # wrong_mode, scope_not_safe — instead of a generic failure.
            raise HomeAssistantError(f"SkyHub refused {command}: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_send("OPEN")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_send("CLOSE")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_send("STOP")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._async_send(position_command(int(kwargs[ATTR_POSITION])))
