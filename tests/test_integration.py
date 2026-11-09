"""Tests d'intégration avec une vraie instance Home Assistant en mémoire."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_priority.const import CONF_DEVICES, DOMAIN

DATA = {
    "solar_power": "sensor.solar",
    "load_power": "sensor.load",
    "battery_power": "sensor.battery",
    "battery_soc": "sensor.soc",
    "tariff_entity": "sensor.tarif",
    "hc_values": "HC",
    "battery_charge_positive": True,
    "allow_battery_discharge": True,
    "battery_discharge_cap": 5000,
    "battery_soc_min": 20,
    "margin": 0,
    "hysteresis": 0,
    "grid_max": 0,
    "scan_interval": 10,
    "settle": 0,
    "hc_boost": True,
    "fail_safe_all_off": True,
}

DEVICES = {
    "clim": {
        "name": "Clim",
        "entity_id": "switch.clim",
        "power": 1000,
        "priority": 1,
        "min_on": 0,
        "min_off": 0,
        "quota": 0,
        "hc_fallback": True,
    },
    "ballon": {
        "name": "Ballon",
        "entity_id": "switch.ballon",
        "power": 2500,
        "priority": 2,
        "min_on": 0,
        "min_off": 0,
        "quota": 0,
        "hc_fallback": True,
    },
}


@pytest.fixture
async def harness(hass: HomeAssistant):
    """Prépare les capteurs et capture les appels de service."""
    calls: list[tuple[str, str, str]] = []

    async def record(call):
        calls.append((call.domain, call.service, call.data.get("entity_id")))

    hass.services.async_register("switch", "turn_on", record)
    hass.services.async_register("switch", "turn_off", record)

    hass.states.async_set("sensor.solar", "3000")
    hass.states.async_set("sensor.load", "0")
    hass.states.async_set("sensor.battery", "0")
    hass.states.async_set("sensor.soc", "80")
    hass.states.async_set("sensor.tarif", "HP")
    hass.states.async_set("switch.clim", "off")
    hass.states.async_set("switch.ballon", "off")

    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options={CONF_DEVICES: DEVICES})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, calls


async def test_setup_creates_entities(hass: HomeAssistant, harness) -> None:
    entry, _ = harness
    assert entry.state.name == "LOADED"
    assert hass.states.get("sensor.energy_priority_puissance_disponible") is not None
    assert hass.states.get("switch.energy_priority_pilotage_automatique") is not None
    assert hass.states.get("select.clim_mode") is not None
    assert hass.states.get("number.ballon_priorite") is not None


async def test_plan_sensor_exposes_devices(hass: HomeAssistant, harness) -> None:
    entry, _ = harness
    state = hass.states.get("sensor.energy_priority_repartition")
    assert state is not None
    attributes = state.attributes
    assert attributes["solaire_w"] == 3000
    assert attributes["budget_w"] is not None
    appareils = {a["nom"]: a for a in attributes["appareils"]}
    assert appareils["Clim"]["accordee"] == 1000
    assert appareils["Clim"]["etat"] is True
    assert appareils["Ballon"]["accordee"] == 0
    assert appareils["Ballon"]["etat"] is False


async def test_priority_allocation(hass: HomeAssistant, harness) -> None:
    entry, calls = harness
    plan = entry.runtime_data.plan
    assert plan is not None
    # 3000 W disponibles : clim (1000) passe, ballon (2000) ne rentre pas
    assert plan.decisions["clim"].turn_on is True
    assert plan.decisions["ballon"].turn_on is False
    assert ("switch", "turn_on", "switch.clim") in calls
    assert ("switch", "turn_on", "switch.ballon") not in calls


async def test_budget_follows_solar(hass: HomeAssistant, harness) -> None:
    entry, _ = harness
    coordinator = entry.runtime_data
    hass.states.async_set("sensor.solar", "4000")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    plan = coordinator.plan
    assert plan.decisions["clim"].turn_on is True
    assert plan.decisions["ballon"].turn_on is True


async def test_battery_soc_floor_blocks_discharge(hass: HomeAssistant, harness) -> None:
    entry, _ = harness
    coordinator = entry.runtime_data
    hass.states.async_set("sensor.solar", "0")
    hass.states.async_set("sensor.battery", "-3000")  # décharge
    hass.states.async_set("sensor.soc", "10")  # sous le seuil de 20 %
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.plan.budget.battery_discharge_w == 0
    assert coordinator.plan.decisions["ballon"].turn_on is False


async def test_control_switch_suspends(hass: HomeAssistant, harness) -> None:
    entry, calls = harness
    coordinator = entry.runtime_data
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.energy_priority_pilotage_automatique"}, blocking=True
    )
    await hass.async_block_till_done()
    assert coordinator.enabled is False
    before = len(calls)
    hass.states.async_set("sensor.solar", "9000")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(calls) == before


async def test_force_off_override(hass: HomeAssistant, harness) -> None:
    entry, calls = harness
    coordinator = entry.runtime_data
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.clim_mode", "option": "Forcé OFF"}, blocking=True
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.plan.decisions["clim"].turn_on is False


async def test_fail_safe_when_sensor_unavailable(hass: HomeAssistant, harness) -> None:
    entry, _ = harness
    coordinator = entry.runtime_data
    hass.states.async_set("switch.clim", "on")
    hass.states.async_set("sensor.solar", "unavailable")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.plan.budget.valid is False
    assert coordinator.plan.decisions["clim"].turn_on is False


async def test_hc_quota_boost_end_to_end(hass: HomeAssistant) -> None:
    """Ballon sans quota atteint : forcé en heures creuses, coupé en heures pleines."""
    calls: list[tuple[str, str, str]] = []

    async def record(call):
        calls.append((call.domain, call.service, call.data.get("entity_id")))

    hass.services.async_register("switch", "turn_on", record)
    hass.services.async_register("switch", "turn_off", record)
    hass.states.async_set("sensor.solar", "0")
    hass.states.async_set("sensor.load", "300")
    hass.states.async_set("sensor.battery", "0")
    hass.states.async_set("sensor.soc", "15")
    hass.states.async_set("sensor.tarif", "HC ..")
    hass.states.async_set("switch.clim", "off")
    hass.states.async_set("switch.ballon", "off")

    devices = {
        "clim": dict(DEVICES["clim"]),
        "ballon": dict(DEVICES["ballon"], quota=2),
    }
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options={CONF_DEVICES: devices})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data
    assert coordinator.hc_active() is True
    assert coordinator.plan.decisions["ballon"].turn_on is True
    assert "heures creuses" in coordinator.plan.decisions["ballon"].reason
    assert coordinator.plan.decisions["clim"].turn_on is False
    assert ("switch", "turn_on", "switch.ballon") in calls

    # retour en heures pleines : plus de forçage
    hass.states.async_set("sensor.tarif", "HP ..")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.hc_active() is False
    assert coordinator.plan.decisions["ballon"].turn_on is False


async def test_manual_switch_on_pauses_control(hass: HomeAssistant, harness) -> None:
    """Un allumage manuel ne doit pas être annulé par le contrôleur."""
    entry, calls = harness
    coordinator = entry.runtime_data

    # le ballon n'a pas été commandé au démarrage : toute bascule est manuelle
    hass.states.async_set("switch.ballon", "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    plan = coordinator.plan
    assert plan.decisions["ballon"].turn_on is True
    assert "grâce manuelle" in plan.decisions["ballon"].reason
    assert ("switch", "turn_off", "switch.ballon") not in calls
