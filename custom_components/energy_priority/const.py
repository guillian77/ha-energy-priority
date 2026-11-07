"""Constantes de l'intégration Energy Priority."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "energy_priority"
VERSION = "1.5.0"

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

CONF_SOLAR = "solar_power"
CONF_LOAD = "load_power"
CONF_BATTERY_POWER = "battery_power"
CONF_BATTERY_SOC = "battery_soc"
CONF_TARIFF = "tariff_entity"
CONF_HC_VALUES = "hc_values"
CONF_BATTERY_SIGN = "battery_charge_positive"
CONF_BATTERY_CAP = "battery_discharge_cap"
CONF_BATTERY_SOC_MIN = "battery_soc_min"
CONF_ALLOW_DISCHARGE = "allow_battery_discharge"
CONF_BATTERY_USE_CAP = "battery_use_cap"
CONF_MARGIN = "margin"
CONF_HYSTERESIS = "hysteresis"
CONF_GRID_MAX = "grid_max"
CONF_FAIL_SAFE = "fail_safe_all_off"
CONF_INTERVAL = "scan_interval"
CONF_HC_BOOST = "hc_boost"
CONF_HC_IGNORE_MIN = "hc_ignore_min_times"
CONF_SETTLE = "settle"
CONF_DEVICES = "devices"

CONF_KEY = "key"
CONF_NAME = "name"
CONF_ENTITY = "entity_id"
CONF_POWER = "power"
CONF_PRIORITY = "priority"
CONF_MIN_ON = "min_on"
CONF_MIN_OFF = "min_off"
CONF_QUOTA = "quota"
CONF_HC_FALLBACK = "hc_fallback"

DEFAULT_HC_VALUES = "HC"
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_SETTLE = 30
DEFAULT_MARGIN = 100
DEFAULT_HYSTERESIS = 150
DEFAULT_BATTERY_CAP = 5000
DEFAULT_BATTERY_SOC_MIN = 20
DEFAULT_DEVICE_PRIORITY = 10
DEFAULT_MIN_ON = 60
DEFAULT_MIN_OFF = 60
DEFAULT_QUOTA = 0.0

STORAGE_VERSION = 1

ATTR_AVAILABLE = "puissance_disponible"
