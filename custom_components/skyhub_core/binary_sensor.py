"""Binary sensors for rain, safety latches and failed closures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkyHubConfigEntry
from .entity import SkyHubEntity
from .model import RoofState


@dataclass(frozen=True, kw_only=True)
class SkyHubBinarySensorDescription(BinarySensorEntityDescription):
    """A binary sensor plus how to read it off a RoofState."""

    value_fn: Callable[[RoofState], bool | None]
    attributes_fn: Callable[[RoofState], dict[str, Any]] | None = None
    # Some readings only exist on firmware that can close on its own.
    requires_rain_auto: bool = False


SENSORS: tuple[SkyHubBinarySensorDescription, ...] = (
    SkyHubBinarySensorDescription(
        key="rain",
        translation_key="rain",
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=lambda roof: roof.rain,
    ),
    SkyHubBinarySensorDescription(
        key="hard_stop",
        translation_key="hard_stop",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda roof: roof.hard_stop,
    ),
    # The one state that needs a person. The controller does not retry a
    # failed rain closure, so the roof can be sitting open in the rain until
    # somebody looks. Worth a notification, not just a tile.
    SkyHubBinarySensorDescription(
        key="rain_closure_failed",
        translation_key="rain_closure_failed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        requires_rain_auto=True,
        value_fn=lambda roof: roof.rain_closure_failed,
        attributes_fn=lambda roof: {
            "close_phase": roof.close_phase,
            "close_block": roof.close_block,
            "close_id": roof.close_id,
        },
    ),
    SkyHubBinarySensorDescription(
        key="rain_closure_active",
        translation_key="rain_closure_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        requires_rain_auto=True,
        value_fn=lambda roof: roof.rain_closure_active,
    ),
    SkyHubBinarySensorDescription(
        key="close_allowed",
        translation_key="close_allowed",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda roof: roof.close_allowed,
    ),
    SkyHubBinarySensorDescription(
        key="position_stale",
        translation_key="position_stale",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda roof: roof.position_stale,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SkyHubConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    roof = coordinator.data
    async_add_entities(
        SkyHubBinarySensor(coordinator, description)
        for description in SENSORS
        if not description.requires_rain_auto or roof.supports_rain_closure
    )


class SkyHubBinarySensor(SkyHubEntity, BinarySensorEntity):
    entity_description: SkyHubBinarySensorDescription

    def __init__(
        self, coordinator, description: SkyHubBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.roof)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.roof)
