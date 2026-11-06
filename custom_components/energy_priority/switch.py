"""Interrupteur global de contrôle."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import EnergyPriorityCoordinator
from .entity import EnergyPriorityEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ControlSwitch(entry.runtime_data)])


class ControlSwitch(EnergyPriorityEntity, SwitchEntity):
    """Active ou suspend le pilotage automatique."""

    _attr_name = "Pilotage automatique"
    _attr_icon = "mdi:lightning-bolt-circle"

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_control"

    @property
    def is_on(self) -> bool:
        return self.coordinator.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.coordinator.enabled = True
        await self.coordinator._save(force=True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        self.coordinator.enabled = False
        await self.coordinator._save(force=True)
        await self.coordinator.async_request_refresh()
