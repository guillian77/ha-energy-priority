"""Capteurs binaires : tarif heures creuses et quota non atteint."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EnergyPriorityCoordinator
from .entity import EnergyPriorityDeviceEntity, EnergyPriorityEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyPriorityCoordinator = entry.runtime_data
    entities: list = [HeuresCreusesSensor(coordinator)]
    for key, config in coordinator.devices.items():
        if config.quota_h > 0:
            entities.append(DeviceQuotaDeficitSensor(coordinator, key))
    async_add_entities(entities)


class HeuresCreusesSensor(EnergyPriorityEntity, BinarySensorEntity):
    """Indique si le tarif heures creuses est actif."""

    _attr_name = "Heures creuses"
    _attr_icon = "mdi:weather-night"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_hc_active"

    @property
    def is_on(self) -> bool:
        return self.coordinator.hc_active()


class DeviceQuotaDeficitSensor(EnergyPriorityDeviceEntity, BinarySensorEntity):
    """Quota journalier non atteint."""

    _attr_name = "Quota non atteint"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_deficit"

    @property
    def is_on(self) -> bool:
        decision = self._decision
        return bool(decision and decision.deficit_s > 0)
