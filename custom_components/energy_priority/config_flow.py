"""Configuration et options de l'intégration Energy Priority."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.data_entry_flow import SectionConfig, section
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_ALLOW_DISCHARGE,
    CONF_BATTERY_CAP,
    CONF_BATTERY_POWER,
    CONF_BATTERY_SIGN,
    CONF_BATTERY_SOC,
    CONF_BATTERY_SOC_MIN,
    CONF_BATTERY_USE_CAP,
    CONF_DEVICES,
    CONF_ENTITY,
    CONF_FAIL_SAFE,
    CONF_GRID,
    CONF_GRID_MAX,
    CONF_HC_BOOST,
    CONF_HC_FALLBACK,
    CONF_HC_IGNORE_MIN,
    CONF_HC_VALUES,
    CONF_HYSTERESIS,
    CONF_INTERVAL,
    CONF_KEY,
    CONF_LOAD,
    CONF_MARGIN,
    CONF_MIN_OFF,
    CONF_MIN_ON,
    CONF_NAME,
    CONF_POWER,
    CONF_PRIORITY,
    CONF_QUOTA,
    CONF_SETTLE,
    CONF_SOLAR,
    CONF_TARIFF,
    CONF_USE_GRID,
    DEFAULT_BATTERY_CAP,
    DEFAULT_BATTERY_SOC_MIN,
    DEFAULT_DEVICE_PRIORITY,
    DEFAULT_HC_VALUES,
    DEFAULT_HYSTERESIS,
    DEFAULT_MARGIN,
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_QUOTA,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SETTLE,
    DOMAIN,
)

POWER = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=30000, step=10, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX)
)
SECONDS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=7200, step=10, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)
)
HOURS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=24, step=0.5, unit_of_measurement="h", mode=selector.NumberSelectorMode.BOX)
)


def _req(key: str, value: Any):
    """Champ obligatoire, avec valeur par défaut seulement si elle existe."""
    if value is None or value == "":
        return vol.Required(key)
    return vol.Required(key, default=value)


def _opt(key: str, value: Any):
    """Champ facultatif, avec valeur par défaut seulement si elle existe."""
    if value is None or value == "":
        return vol.Optional(key)
    return vol.Optional(key, default=value)


def _settings_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Formulaire des réglages globaux, organisé en sections thématiques."""
    sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    watts = POWER

    def bloc_capteurs() -> vol.Schema:
        return vol.Schema(
            {
                _req(CONF_SOLAR, defaults.get(CONF_SOLAR)): sensor,
                _req(CONF_LOAD, defaults.get(CONF_LOAD)): sensor,
                _opt(CONF_BATTERY_POWER, defaults.get(CONF_BATTERY_POWER)): sensor,
                _opt(CONF_BATTERY_SOC, defaults.get(CONF_BATTERY_SOC)): sensor,
                _opt(CONF_GRID, defaults.get(CONF_GRID)): sensor,
                _opt(CONF_TARIFF, defaults.get(CONF_TARIFF)): sensor,
                vol.Optional(
                    CONF_HC_VALUES, default=defaults.get(CONF_HC_VALUES, DEFAULT_HC_VALUES)
                ): str,
            }
        )

    def bloc_batterie() -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_BATTERY_SIGN, default=defaults.get(CONF_BATTERY_SIGN, True)
                ): bool,
                vol.Optional(
                    CONF_ALLOW_DISCHARGE, default=defaults.get(CONF_ALLOW_DISCHARGE, True)
                ): bool,
                vol.Optional(
                    CONF_BATTERY_USE_CAP, default=defaults.get(CONF_BATTERY_USE_CAP, False)
                ): bool,
                vol.Optional(
                    CONF_BATTERY_CAP, default=defaults.get(CONF_BATTERY_CAP, DEFAULT_BATTERY_CAP)
                ): watts,
                vol.Optional(
                    CONF_BATTERY_SOC_MIN,
                    default=defaults.get(CONF_BATTERY_SOC_MIN, DEFAULT_BATTERY_SOC_MIN),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )

    def bloc_budget() -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_USE_GRID, default=defaults.get(CONF_USE_GRID, False)
                ): bool,
                vol.Optional(
                    CONF_MARGIN, default=defaults.get(CONF_MARGIN, DEFAULT_MARGIN)
                ): watts,
                vol.Optional(
                    CONF_HYSTERESIS, default=defaults.get(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)
                ): watts,
                vol.Optional(
                    CONF_GRID_MAX, default=defaults.get(CONF_GRID_MAX, 0)
                ): watts,
                vol.Optional(
                    CONF_INTERVAL, default=defaults.get(CONF_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=300, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_SETTLE, default=defaults.get(CONF_SETTLE, DEFAULT_SETTLE)
                ): SECONDS,
            }
        )

    def bloc_hc() -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_HC_BOOST, default=defaults.get(CONF_HC_BOOST, True)
                ): bool,
                vol.Optional(
                    CONF_HC_IGNORE_MIN, default=defaults.get(CONF_HC_IGNORE_MIN, True)
                ): bool,
            }
        )

    def bloc_securite() -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_FAIL_SAFE, default=defaults.get(CONF_FAIL_SAFE, True)
                ): bool,
            }
        )

    return vol.Schema(
        {
            vol.Required("capteurs"): section(bloc_capteurs(), SectionConfig({"collapsed": False})),
            vol.Required("batterie"): section(bloc_batterie(), SectionConfig({"collapsed": False})),
            vol.Required("budget"): section(bloc_budget(), SectionConfig({"collapsed": False})),
            vol.Required("heures_creuses"): section(bloc_hc(), SectionConfig({"collapsed": True})),
            vol.Required("securite"): section(bloc_securite(), SectionConfig({"collapsed": True})),
        }
    )


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Aplatit les sections du formulaire (compatibilité avec l'ancien format)."""
    plat: dict[str, Any] = {}
    for cle, valeur in user_input.items():
        if isinstance(valeur, dict):
            plat.update(valeur)
        else:
            plat[cle] = valeur
    return plat


def _device_schema(
    defaults: dict[str, Any], with_more: bool = True, first_run: bool = False
) -> vol.Schema:
    """Formulaire d'un appareil (facultatif au premier lancement)."""
    entity_selector = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=["switch", "climate", "water_heater", "input_boolean"]
        )
    )
    fields: dict[Any, Any] = {
        (
            vol.Optional(CONF_ENTITY)
            if first_run
            else _req(CONF_ENTITY, defaults.get(CONF_ENTITY))
        ): entity_selector,
        vol.Optional(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
        vol.Required(CONF_POWER, default=defaults.get(CONF_POWER, 1000)): POWER,
        vol.Required(CONF_PRIORITY, default=defaults.get(CONF_PRIORITY, DEFAULT_DEVICE_PRIORITY)): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_MIN_ON, default=defaults.get(CONF_MIN_ON, DEFAULT_MIN_ON)): SECONDS,
        vol.Optional(CONF_MIN_OFF, default=defaults.get(CONF_MIN_OFF, DEFAULT_MIN_OFF)): SECONDS,
        vol.Optional(CONF_QUOTA, default=defaults.get(CONF_QUOTA, DEFAULT_QUOTA)): HOURS,
        vol.Optional(CONF_HC_FALLBACK, default=defaults.get(CONF_HC_FALLBACK, True)): bool,
    }
    if with_more:
        fields[vol.Optional("add_another", default=False)] = bool
    return vol.Schema(fields)


def _clean_devices(value: Any) -> dict[str, Any]:
    return {k: dict(v) for k, v in (value or {}).items()}


class EnergyPriorityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création de l'instance."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Retourne le gestionnaire d'options."""
        return EnergyPriorityOptionsFlow()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._devices: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            self._data = _flatten(user_input)
            return await self.async_step_device()
        return self.async_show_form(step_id="user", data_schema=_settings_schema({}))

    async def async_step_device(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            add_another = bool(user_input.pop("add_another", False))
            if user_input.get(CONF_ENTITY):
                self._devices.update(self._build_device(user_input))
            if add_another:
                return await self.async_step_device()
            return self.async_create_entry(
                title="Energy Priority",
                data=self._data,
                options={CONF_DEVICES: self._devices},
            )
        return self.async_show_form(
            step_id="device",
            data_schema=_device_schema({}, first_run=not self._devices),
            errors=errors,
            description_placeholders={"info": "Ajoutez un premier appareil (facultatif)."},
        )

    @staticmethod
    def _build_device(user_input: dict[str, Any]) -> dict[str, Any]:
        entity_id: str = user_input[CONF_ENTITY]
        key = slugify(user_input.get(CONF_NAME) or entity_id.split(".")[-1]) or "appareil"
        payload = {
            CONF_NAME: user_input.get(CONF_NAME) or entity_id.split(".")[-1].replace("_", " ").title(),
            CONF_ENTITY: entity_id,
            CONF_POWER: float(user_input[CONF_POWER]),
            CONF_PRIORITY: int(user_input[CONF_PRIORITY]),
            CONF_MIN_ON: int(user_input.get(CONF_MIN_ON, DEFAULT_MIN_ON)),
            CONF_MIN_OFF: int(user_input.get(CONF_MIN_OFF, DEFAULT_MIN_OFF)),
            CONF_QUOTA: float(user_input.get(CONF_QUOTA, DEFAULT_QUOTA)),
            CONF_HC_FALLBACK: bool(user_input.get(CONF_HC_FALLBACK, True)),
        }
        return {key: payload}


class EnergyPriorityOptionsFlow(OptionsFlow):
    """Gestion des réglages et des appareils après installation."""

    def __init__(self) -> None:
        self._key: str | None = None

    @property
    def _coordinator(self):
        return self.config_entry.runtime_data

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "add_device", "edit_device", "remove_device"],
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(_flatten(user_input))
            return self.async_create_entry(title="", data=options)
        defaults = dict(self.config_entry.data)
        defaults.update(self.config_entry.options)
        return self.async_show_form(step_id="settings", data_schema=_settings_schema(defaults))

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            add_another = bool(user_input.pop("add_another", False))
            devices = _clean_devices(self.config_entry.options.get(CONF_DEVICES))
            new = EnergyPriorityConfigFlow._build_device(user_input)
            key = next(iter(new))
            while key in devices:
                key = f"{key}_2"
                new = {key: new[next(iter(new))]}
            devices.update(new)
            options = dict(self.config_entry.options)
            options[CONF_DEVICES] = devices
            if add_another:
                self._key = None
                return await self.async_step_add_device()
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(step_id="add_device", data_schema=_device_schema({}), errors=errors)

    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None):
        devices = _clean_devices(self.config_entry.options.get(CONF_DEVICES))
        if not devices:
            return self.async_abort(reason="no_devices")

        if self._key is None:
            if user_input is not None:
                self._key = user_input[CONF_KEY]
            else:
                return self.async_show_form(
                    step_id="edit_device",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_KEY): selector.SelectSelector(
                                selector.SelectSelectorConfig(
                                    options=[
                                        selector.SelectOptionDict(value=k, label=v.get(CONF_NAME, k))
                                        for k, v in devices.items()
                                    ],
                                    mode=selector.SelectSelectorMode.LIST,
                                )
                            )
                        }
                    ),
                )

        current = dict(devices[self._key])
        if user_input is not None and CONF_ENTITY in user_input:
            current.update({k: v for k, v in user_input.items() if k in current or k == CONF_ENTITY})
            current.pop("add_another", None)
            devices[self._key] = current
            options = dict(self.config_entry.options)
            options[CONF_DEVICES] = devices
            self._key = None
            return self.async_create_entry(title="", data=options)

        schema_defaults = {
            CONF_ENTITY: current.get(CONF_ENTITY),
            CONF_NAME: current.get(CONF_NAME, ""),
            CONF_POWER: current.get(CONF_POWER, 1000),
            CONF_PRIORITY: current.get(CONF_PRIORITY, DEFAULT_DEVICE_PRIORITY),
            CONF_MIN_ON: current.get(CONF_MIN_ON, DEFAULT_MIN_ON),
            CONF_MIN_OFF: current.get(CONF_MIN_OFF, DEFAULT_MIN_OFF),
            CONF_QUOTA: current.get(CONF_QUOTA, DEFAULT_QUOTA),
            CONF_HC_FALLBACK: current.get(CONF_HC_FALLBACK, True),
        }
        return self.async_show_form(
            step_id="edit_device",
            data_schema=_device_schema(schema_defaults, with_more=False),
            description_placeholders={"name": current.get(CONF_NAME, self._key)},
        )

    async def async_step_remove_device(self, user_input: dict[str, Any] | None = None):
        devices = _clean_devices(self.config_entry.options.get(CONF_DEVICES))
        if not devices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            devices.pop(user_input[CONF_KEY], None)
            options = dict(self.config_entry.options)
            options[CONF_DEVICES] = devices
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="remove_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KEY): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=k, label=v.get(CONF_NAME, k))
                                for k, v in devices.items()
                            ],
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )
