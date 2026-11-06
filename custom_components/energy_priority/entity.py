"""Classes de base des entités Energy Priority."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VERSION
from .coordinator import EnergyPriorityCoordinator


class EnergyPriorityEntity(CoordinatorEntity[EnergyPriorityCoordinator]):
    """Entité rattachée au contrôleur global."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        entry_id = coordinator.entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Energy Priority",
            manufacturer="Intégration personnalisée",
            model="Contrôleur de priorité énergétique",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
        )


class EnergyPriorityDeviceEntity(EnergyPriorityEntity):
    """Entité rattachée à un appareil piloté."""

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        config = coordinator.devices[key]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{key}")},
            name=config.name,
            manufacturer="Energy Priority",
            model="Appareil piloté",
            via_device=(DOMAIN, coordinator.entry.entry_id),
        )

    @property
    def _config(self):
        return self.coordinator.devices.get(self._key)

    @property
    def _decision(self):
        plan = self.coordinator.plan
        return plan.decisions.get(self._key) if plan else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._config is not None
