"""Réglages numériques par appareil : priorité et quota."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_PRIORITY, CONF_QUOTA
from .coordinator import EnergyPriorityCoordinator
from .entity import EnergyPriorityDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyPriorityCoordinator = entry.runtime_data
    entities = []
    for key in coordinator.devices:
        entities.append(DevicePriorityNumber(coordinator, key))
        entities.append(DeviceQuotaNumber(coordinator, key))
    async_add_entities(entities)


class DevicePriorityNumber(EnergyPriorityDeviceEntity, NumberEntity):
    """Priorité de l'appareil (1 = le plus critique)."""

    _attr_name = "Priorité"
    _attr_icon = "mdi:sort-numeric-ascending"
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_priority"

    @property
    def native_value(self) -> float | None:
        config = self._config
        return float(config.priority) if config else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device(self._key, **{CONF_PRIORITY: int(value)})
        self.async_write_ha_state()


class DeviceQuotaNumber(EnergyPriorityDeviceEntity, NumberEntity):
    """Quota de marche quotidien (0 = désactivé)."""

    _attr_name = "Quota journalier"
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 0
    _attr_native_max_value = 24
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_quota"

    @property
    def native_value(self) -> float | None:
        config = self._config
        return float(config.quota_h) if config else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_device(self._key, **{CONF_QUOTA: float(value)})
        self.async_write_ha_state()
