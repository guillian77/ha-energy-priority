"""Capteurs : budget disponible et état de chaque appareil."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import EnergyPriorityCoordinator
from .entity import EnergyPriorityDeviceEntity, EnergyPriorityEntity
from .scheduler import Override


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: EnergyPriorityCoordinator = entry.runtime_data
    entities: list = [
        EnergyPlanSensor(coordinator),
        AvailablePowerSensor(coordinator),
        BaseLoadSensor(coordinator),
        GridImportSensor(coordinator),
    ]
    for key in coordinator.devices:
        entities.append(DeviceAllocatedSensor(coordinator, key))
        entities.append(DeviceRuntimeSensor(coordinator, key))
        entities.append(DeviceDecisionSensor(coordinator, key))
    async_add_entities(entities)


class _PowerSensor(EnergyPriorityEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def _budget(self):
        plan = self.coordinator.plan
        return plan.budget if plan else None


class AvailablePowerSensor(_PowerSensor):
    """Puissance encore disponible pour les appareils pilotés."""

    _attr_name = "Puissance disponible"
    _attr_icon = "mdi:battery-plus-variant"

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_available_power"

    @property
    def native_value(self) -> float | None:
        budget = self._budget()
        return budget.available_w if budget and budget.valid else None

    @property
    def extra_state_attributes(self):
        budget = self._budget()
        if not budget:
            return {}
        return {
            "charge_de_base": budget.base_load_w,
            "decharge_batterie_autorisee": budget.battery_discharge_w,
            "budget_valide": budget.valid,
            "raison": budget.reason,
        }


class BaseLoadSensor(_PowerSensor):
    """Consommation hors appareils pilotés."""

    _attr_name = "Charge de base"
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_base_load"

    @property
    def native_value(self) -> float | None:
        budget = self._budget()
        return budget.base_load_w if budget and budget.valid else None


class GridImportSensor(_PowerSensor):
    """Puissance importée estimée depuis le réseau."""

    _attr_name = "Import réseau estimé"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_grid_import"

    @property
    def native_value(self) -> float | None:
        budget = self._budget()
        return budget.grid_import_w if budget and budget.valid else None


class DeviceAllocatedSensor(EnergyPriorityDeviceEntity, SensorEntity):
    """Puissance accordée à l'appareil par le plan courant."""

    _attr_name = "Puissance accordée"
    _attr_icon = "mdi:flash"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_allocated"

    @property
    def native_value(self) -> float:
        decision = self._decision
        config = self._config
        if decision is None or config is None or not decision.turn_on:
            return 0
        return config.power_w


class DeviceRuntimeSensor(EnergyPriorityDeviceEntity, SensorEntity):
    """Temps de marche cumulé sur les 24 dernières heures."""

    _attr_name = "Marche 24 h"
    _attr_icon = "mdi:clock-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "h"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_runtime"

    @property
    def native_value(self) -> float:
        tracker = self.coordinator.trackers.get(self._key)
        if tracker is None:
            return 0
        return round(tracker.runtime(dt_util.utcnow().timestamp()) / 3600, 2)


class DeviceDecisionSensor(EnergyPriorityDeviceEntity, SensorEntity):
    """Motif de la dernière décision."""

    _attr_name = "Décision"
    _attr_icon = "mdi:head-cog-outline"

    def __init__(self, coordinator: EnergyPriorityCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_decision"

    @property
    def native_value(self) -> str:
        decision = self._decision
        if decision is None:
            return "aucune décision"
        return "Marche" if decision.turn_on else "Arrêt"

    @property
    def extra_state_attributes(self):
        decision = self._decision
        config = self._config
        if decision is None or config is None:
            return {}
        return {
            "raison": decision.reason,
            "puissance_nominale": config.power_w,
            "priorite": config.priority,
            "quota_h": config.quota_h,
            "quota_restant_h": round(decision.deficit_s / 3600, 2),
            "mode": self.coordinator.overrides.get(self._key, Override.AUTO).value,
        }


class EnergyPlanSensor(EnergyPriorityEntity, SensorEntity):
    """État complet du plan, consommé par la carte de tableau de bord."""

    _attr_name = "Répartition"
    _attr_icon = "mdi:chart-donut-variant"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: EnergyPriorityCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_plan"

    @property
    def native_value(self) -> float:
        plan = self.coordinator.plan
        return plan.used_w if plan else 0

    @property
    def extra_state_attributes(self) -> dict:
        coordinator = self.coordinator
        plan = coordinator.plan
        inputs = coordinator.inputs
        if plan is None:
            return {}

        appareils = []
        for key, config in coordinator.devices.items():
            decision = plan.decisions.get(key)
            tracker = coordinator.trackers.get(key)
            override = coordinator.overrides.get(key, Override.AUTO)
            appareils.append(
                {
                    "cle": key,
                    "nom": config.name,
                    "entite": config.entity_id,
                    "puissance": config.power_w,
                    "accordee": config.power_w if decision and decision.turn_on else 0,
                    "priorite": config.priority,
                    "etat": bool(decision and decision.turn_on),
                    "raison": decision.reason if decision else "",
                    "quota_h": config.quota_h,
                    "marche_24h_h": round(
                        tracker.runtime(dt_util.utcnow().timestamp()) / 3600, 2
                    )
                    if tracker
                    else 0,
                    "mode": override.value,
                    "quota_restant_h": round(decision.deficit_s / 3600, 2)
                    if decision
                    else 0,
                }
            )
        appareils.sort(key=lambda item: (item["priorite"], item["nom"]))

        return {
            "solaire_w": inputs.solar_w if inputs else None,
            "consommation_w": inputs.load_w if inputs else None,
            "batterie_w": inputs.battery_w if inputs else None,
            "batterie_soc": inputs.battery_soc if inputs else None,
            "heures_creuses": inputs.hc_active if inputs else False,
            "reseau_w": plan.budget.grid_import_w if plan.budget.valid else None,
            "budget_w": plan.budget.available_w if plan.budget.valid else None,
            "charge_de_base_w": plan.budget.base_load_w,
            "decharge_autorisee_w": plan.budget.battery_discharge_w,
            "appareils": appareils,
        }
