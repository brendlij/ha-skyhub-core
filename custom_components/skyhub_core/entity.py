"""Shared base for every SkyHub entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SkyHubCoordinator
from .model import RoofState


class SkyHubEntity(CoordinatorEntity[SkyHubCoordinator]):
    """One entity belonging to the roof device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkyHubCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=coordinator.client.host,
        )

    @property
    def roof(self) -> RoofState:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Unavailable covers both a silent SkyHub and a silent controller.

        SkyHub answers with available=false when the serial link to the
        controller is down. Showing a stale roof position as if it were
        current would be worse than showing nothing.
        """
        return super().available and self.roof.available
