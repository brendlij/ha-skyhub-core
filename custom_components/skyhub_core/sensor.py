"""Diagnostic sensors describing the last rain closure."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkyHubConfigEntry
from .entity import SkyHubEntity
from .model import (
    PHASE_BLOCKED,
    PHASE_CLOSED,
    PHASE_CLOSING,
    PHASE_ERROR,
    PHASE_EXPIRED,
    PHASE_IDLE,
    PHASE_INTERRUPTED,
    PHASE_PENDING,
    PHASE_STOPPING,
    RoofState,
)


@dataclass(frozen=True, kw_only=True)
class SkyHubSensorDescription(SensorEntityDescription):
    value_fn: Callable[[RoofState], str | int | None]
    requires_rain_auto: bool = False
    requires_closure_report: bool = False


SENSORS: tuple[SkyHubSensorDescription, ...] = (
    SkyHubSensorDescription(
        key="close_phase",
        translation_key="close_phase",
        device_class="enum",
        options=[
            PHASE_IDLE,
            PHASE_PENDING,
            PHASE_STOPPING,
            PHASE_BLOCKED,
            PHASE_CLOSING,
            PHASE_CLOSED,
            PHASE_INTERRUPTED,
            PHASE_EXPIRED,
            PHASE_ERROR,
        ],
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_closure_report=True,
        value_fn=lambda roof: roof.close_phase or None,
    ),
    SkyHubSensorDescription(
        key="close_block",
        translation_key="close_block",
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_closure_report=True,
        # "none" is the firmware's way of saying nothing blocked it; an
        # empty sensor reads better in Home Assistant than the word none.
        value_fn=lambda roof: (
            None if roof.close_block in ("", "none") else roof.close_block
        ),
    ),
    SkyHubSensorDescription(
        key="close_reason",
        translation_key="close_reason",
        entity_category=EntityCategory.DIAGNOSTIC,
        requires_closure_report=True,
        value_fn=lambda roof: (
            None if roof.close_reason in ("", "none") else roof.close_reason
        ),
    ),
    SkyHubSensorDescription(
        key="driver",
        translation_key="driver",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda roof: roof.driver or None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SkyHubConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    roof = coordinator.data
    async_add_entities(
        SkyHubSensor(coordinator, description)
        for description in SENSORS
        if (not description.requires_rain_auto or roof.supports_rain_closure)
        and (not description.requires_closure_report or roof.reports_closure)
    )


class SkyHubSensor(SkyHubEntity, SensorEntity):
    entity_description: SkyHubSensorDescription

    def __init__(self, coordinator, description: SkyHubSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | None:
        return self.entity_description.value_fn(self.roof)
