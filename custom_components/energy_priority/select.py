"""Mode de chaque appareil : auto / forcé ON / forcé OFF."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EnergyPriorityCoordinator
from .entity import EnergyPriorityDeviceEntity
from .scheduler import Override

LABELS = {
    Override.AUTO: "Auto",
    Override.FORCE_ON: "Forcé ON",
    Override.FORCE_OFF: "Forcé OFF",
}
VALUES = {label: override for override, label in LABELS.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyPriorityCoordinator = entry.runtime_data
    async_add_entities(DeviceModeSelect(coordinator, key) for key in coordinator.devices)


class DeviceModeSelect(EnergyPriorityDeviceEntity, SelectEntity):
    """Mode manuel de l'appareil."""

    _attr_name = "Mode"
    _attr_icon = "mdi:tune-variant"
    _attr_options = list(VALUES)

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_mode"

    @property
    def current_option(self) -> str:
        override = self.coordinator.overrides.get(self._key, Override.AUTO)
        return LABELS[override]

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_override(self._key, VALUES[option])
        self.async_write_ha_state()
