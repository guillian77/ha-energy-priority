"""Vérifie les parcours de configuration (installation et options)."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_priority.const import CONF_DEVICES, DOMAIN

USER_INPUT = {
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
    "margin": 100,
    "hysteresis": 150,
    "grid_max": 0,
    "scan_interval": 10,
    "settle": 30,
    "hc_boost": True,
    "fail_safe_all_off": True,
}

DEVICE_INPUT = {
    "entity_id": "switch.ballon",
    "name": "Ballon",
    "power": 2000,
    "priority": 2,
    "min_on": 1800,
    "min_off": 60,
    "quota": 2,
    "hc_fallback": True,
    "add_another": False,
}


FORM_INPUT = {
    "capteurs": {
        "solar_power": "sensor.solar",
        "load_power": "sensor.load",
        "battery_power": "sensor.battery",
        "battery_soc": "sensor.soc",
        "tariff_entity": "sensor.tarif",
        "hc_values": "HC",
    },
    "batterie": {
        "battery_charge_positive": True,
        "allow_battery_discharge": True,
        "battery_use_cap": False,
        "battery_discharge_cap": 5000,
        "battery_soc_min": 20,
        "battery_reserve_soc": 60,
        "battery_no_budget_when_charging": True,
    },
    "budget": {
        "use_measured_grid": False,
        "margin": 100,
        "hysteresis": 150,
        "grid_max": 0,
        "scan_interval": 10,
        "settle": 30,
    },
    "heures_creuses": {"hc_boost": True, "hc_ignore_min_times": True},
    "securite": {"fail_safe_all_off": True},
}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM_INPUT)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "device"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], DEVICE_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_DEVICES]["ballon"]["power"] == 2000.0


async def test_user_flow_without_device(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM_INPUT)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": False}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_options_flow_add_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, options={CONF_DEVICES: {}})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.solar", "1000")
    hass.states.async_set("sensor.load", "0")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_device"}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], DEVICE_INPUT)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert "ballon" in entry.options[CONF_DEVICES]


async def test_options_settings_sections_are_flattened(hass: HomeAssistant) -> None:
    """Les sections du formulaire sont aplaties dans les options."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, options={CONF_DEVICES: {}})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.solar", "1000")
    hass.states.async_set("sensor.load", "0")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["type"] == FlowResultType.FORM

    nouveau = {k: dict(v) for k, v in FORM_INPUT.items()}
    nouveau["budget"]["hysteresis"] = 300
    nouveau["budget"]["margin"] = 50
    result = await hass.config_entries.options.async_configure(result["flow_id"], nouveau)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["hysteresis"] == 300
    assert entry.options["margin"] == 50
    assert "budget" not in entry.options
    assert entry.options["battery_reserve_soc"] == 60
    assert entry.options["battery_no_budget_when_charging"] is True


async def test_battery_guard_defaults_when_omitted(hass: HomeAssistant) -> None:
    """Sans saisie, la réserve reste désactivée et la charge n'est pas comptée."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, options={CONF_DEVICES: {}})
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.solar", "1000")
    hass.states.async_set("sensor.load", "0")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    partiel = {k: dict(v) for k, v in FORM_INPUT.items()}
    partiel["batterie"].pop("battery_reserve_soc")
    partiel["batterie"].pop("battery_no_budget_when_charging")
    result = await hass.config_entries.options.async_configure(result["flow_id"], partiel)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options["battery_reserve_soc"] == 0
    assert entry.options["battery_no_budget_when_charging"] is True


def test_battery_section_order_keeps_guards_together() -> None:
    """L'ordre du formulaire Batterie : les deux garde-fous côte à côte.

    « Compter la batterie pour son plafond » et « Ne pas compter pendant la
    charge » se lisent ensemble : le second suit immédiatement le premier.
    """
    from custom_components.energy_priority.config_flow import _settings_schema

    section_batterie = _settings_schema({}).schema["batterie"]
    ordre = list(section_batterie.schema.schema)
    assert ordre[:5] == [
        "battery_charge_positive",
        "allow_battery_discharge",
        "battery_use_cap",
        "battery_no_budget_when_charging",
        "battery_discharge_cap",
    ]
