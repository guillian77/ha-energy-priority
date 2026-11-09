"""Coordinateur : lecture des capteurs, décision, application."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

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
    CONF_MANUAL_GRACE,
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
    DEFAULT_MANUAL_GRACE,
    DEFAULT_MARGIN,
    DEFAULT_MIN_OFF,
    DEFAULT_MIN_ON,
    DEFAULT_QUOTA,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SETTLE,
    DOMAIN,
    STORAGE_VERSION,
)
from .scheduler import (
    DeviceConfig,
    DevicePhase,
    DeviceSnapshot,
    Inputs,
    Override,
    Plan,
    Settings,
    build_plan,
)

_LOGGER = logging.getLogger(__name__)

RUNTIME_WINDOW = 24 * 3600
SAVE_INTERVAL = 60


@dataclass
class RuntimeTracker:
    """Suivi du temps de marche réel (fenêtre glissante de 24 h)."""

    segments: list[list[float]] = field(default_factory=list)
    phase: DevicePhase = DevicePhase.UNKNOWN
    last_change: float = 0.0
    last_command: float = 0.0
    last_command_wall: float = 0.0
    manual_until: float = 0.0

    def update(self, phase: DevicePhase, now: float) -> None:
        if phase == self.phase:
            return
        if self.phase == DevicePhase.ON and self.segments and self.segments[-1][1] == 0.0:
            self.segments[-1][1] = now
        if phase == DevicePhase.ON:
            self.segments.append([now, 0.0])
        self.phase = phase
        self.last_change = now

    def runtime(self, now: float, window: float = RUNTIME_WINDOW) -> float:
        total = 0.0
        floor = now - window
        for start, end in self.segments:
            effective_end = end if end else now
            if effective_end <= floor:
                continue
            total += effective_end - max(start, floor)
        return total

    def on_duration(self, now: float) -> float:
        return now - self.last_change if self.phase == DevicePhase.ON else 0.0

    def off_duration(self, now: float) -> float:
        if self.phase == DevicePhase.OFF:
            return now - self.last_change
        if self.phase == DevicePhase.UNKNOWN:
            return 1e9
        return 0.0

    def prune(self, now: float, window: float = RUNTIME_WINDOW) -> None:
        self.segments = [
            seg for seg in self.segments if seg[1] == 0.0 or seg[1] > now - window
        ][-500:]

    def dump(self) -> list[list[float]]:
        return [[seg[0], seg[1]] for seg in self.segments]


class EnergyPriorityCoordinator(DataUpdateCoordinator[Plan]):
    """Coordonne les capteurs et pilote les appareils."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.devices: dict[str, DeviceConfig] = {}
        self.trackers: dict[str, RuntimeTracker] = {}
        self.overrides: dict[str, Override] = {}
        self.enabled = True
        self.plan: Plan | None = None
        self.inputs: Inputs | None = None
        self._last_save = 0.0
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        interval = self._cfg(CONF_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(5, int(interval))),
        )

    # ------------------------------------------------------------------ config
    def _cfg(self, key: str, default):
        value = self.entry.options.get(key, self.entry.data.get(key, default))
        return default if value is None else value

    def _settings(self) -> Settings:
        grid_max = self._cfg(CONF_GRID_MAX, 0)
        return Settings(
            battery_charge_positive=bool(self._cfg(CONF_BATTERY_SIGN, True)),
            battery_discharge_cap_w=float(self._cfg(CONF_BATTERY_CAP, DEFAULT_BATTERY_CAP)),
            allow_battery_discharge=bool(self._cfg(CONF_ALLOW_DISCHARGE, True)),
            battery_use_cap=bool(self._cfg(CONF_BATTERY_USE_CAP, False)),
            battery_soc_min=float(self._cfg(CONF_BATTERY_SOC_MIN, DEFAULT_BATTERY_SOC_MIN)),
            margin_w=float(self._cfg(CONF_MARGIN, DEFAULT_MARGIN)),
            hysteresis_w=float(self._cfg(CONF_HYSTERESIS, DEFAULT_HYSTERESIS)),
            grid_max_w=float(grid_max) if grid_max else None,
            fail_safe_all_off=bool(self._cfg(CONF_FAIL_SAFE, True)),
            hc_ignore_min_times=bool(self._cfg(CONF_HC_IGNORE_MIN, True)),
            use_measured_grid=bool(self._cfg(CONF_USE_GRID, False)),
        )

    def _load_devices(self) -> None:
        raw = self._cfg(CONF_DEVICES, {}) or {}
        devices: dict[str, DeviceConfig] = {}
        for key, item in raw.items():
            if not item.get(CONF_ENTITY):
                continue
            devices[key] = DeviceConfig(
                key=key,
                name=item.get(CONF_NAME, key),
                entity_id=item[CONF_ENTITY],
                power_w=float(item.get(CONF_POWER, 0)),
                priority=int(item.get(CONF_PRIORITY, DEFAULT_DEVICE_PRIORITY)),
                min_on_s=int(item.get(CONF_MIN_ON, DEFAULT_MIN_ON)),
                min_off_s=int(item.get(CONF_MIN_OFF, DEFAULT_MIN_OFF)),
                quota_h=float(item.get(CONF_QUOTA, DEFAULT_QUOTA)),
                hc_fallback=bool(item.get(CONF_HC_FALLBACK, True)),
            )
        self.devices = devices

    async def async_update_device(self, key: str, **changes) -> None:
        raw = {k: dict(v) for k, v in (self._cfg(CONF_DEVICES, {}) or {}).items()}
        if key in raw:
            raw[key].update(changes)
            await self.async_set_option(CONF_DEVICES, raw)

    async def async_remove_device(self, key: str) -> None:
        raw = {k: dict(v) for k, v in (self._cfg(CONF_DEVICES, {}) or {}).items()}
        raw.pop(key, None)
        await self.async_set_option(CONF_DEVICES, raw)

    async def async_set_option(self, key: str, value) -> None:
        options = dict(self.entry.options)
        options[key] = value
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self._load_devices()
        await self.async_request_refresh()

    async def async_set_override(self, key: str, override: Override) -> None:
        self.overrides[key] = override
        await self._save(force=True)
        await self.async_request_refresh()

    # ------------------------------------------------------------------ sensors
    def _state_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            value = state.attributes.get("value")
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

    def hc_active(self) -> bool:
        entity_id = self._cfg(CONF_TARIFF, None)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        values = str(self._cfg(CONF_HC_VALUES, DEFAULT_HC_VALUES) or DEFAULT_HC_VALUES)
        tokens = [token.strip().upper() for token in values.split(",") if token.strip()]
        current = state.state.strip().upper()
        return any(current.startswith(token) for token in tokens)

    def _read_inputs(self) -> Inputs:
        return Inputs(
            solar_w=self._state_float(self._cfg(CONF_SOLAR, None)),
            load_w=self._state_float(self._cfg(CONF_LOAD, None)),
            battery_w=self._state_float(self._cfg(CONF_BATTERY_POWER, None)),
            battery_soc=self._state_float(self._cfg(CONF_BATTERY_SOC, None)),
            grid_w=self._state_float(self._cfg(CONF_GRID, None)),
            hc_active=self.hc_active(),
        )

    def _read_device(self, entity_id: str) -> tuple[DevicePhase, bool]:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return DevicePhase.UNKNOWN, False
        domain = entity_id.split(".", 1)[0]
        if domain == "climate":
            return (
                DevicePhase.OFF if state.state == STATE_OFF else DevicePhase.ON
            ), True
        return (DevicePhase.ON if state.state == STATE_ON else DevicePhase.OFF), True

    # ------------------------------------------------------------------- update
    async def _async_update_data(self) -> Plan:
        self._load_devices()
        now = dt_util.utcnow().timestamp()
        inputs = self._read_inputs()
        self.inputs = inputs

        pairs: list[tuple[DeviceConfig, DeviceSnapshot]] = []
        for key, config in self.devices.items():
            tracker = self.trackers.setdefault(key, RuntimeTracker())
            phase, available = self._read_device(config.entity_id)
            self._detecter_action_manuelle(tracker, phase, now)
            tracker.update(phase, now)
            tracker.prune(now)
            pairs.append(
                (
                    config,
                    DeviceSnapshot(
                        phase=phase,
                        on_duration_s=tracker.on_duration(now),
                        off_duration_s=tracker.off_duration(now),
                        runtime_24h_s=tracker.runtime(now),
                        override=self.overrides.get(key, Override.AUTO),
                        available=available,
                        grace_s=max(0.0, tracker.manual_until - now),
                    ),
                )
            )

        plan = build_plan(
            pairs,
            inputs,
            self._settings(),
            hc_boost_enabled=bool(self._cfg(CONF_HC_BOOST, True)),
            now=now,
        )
        self.plan = plan

        if self.enabled:
            await self._apply(plan, now)
        else:
            for decision in plan.decisions.values():
                decision.reason = "contrôle désactivé"

        await self._save()
        return plan

    def _detecter_action_manuelle(
        self, tracker: RuntimeTracker, phase: DevicePhase, now: float
    ) -> None:
        """Une bascule non commandée par l'intégration ouvre une grâce manuelle."""
        grace = float(self._cfg(CONF_MANUAL_GRACE, DEFAULT_MANUAL_GRACE))
        if grace <= 0:
            return
        if phase == tracker.phase or tracker.phase == DevicePhase.UNKNOWN:
            return
        settle = float(self._cfg(CONF_SETTLE, DEFAULT_SETTLE))
        if tracker.last_command_wall and now - tracker.last_command_wall <= settle + 5:
            return
        tracker.manual_until = now + grace
        _LOGGER.debug(
            "Action manuelle détectée (état %s), pilotage suspendu %s s", phase, int(grace)
        )

    async def _apply(self, plan: Plan, now: float) -> None:
        settle = float(self._cfg(CONF_SETTLE, DEFAULT_SETTLE))
        for key, decision in plan.decisions.items():
            config = self.devices.get(key)
            tracker = self.trackers.get(key)
            if config is None or tracker is None:
                continue
            current_on = tracker.phase == DevicePhase.ON
            if decision.turn_on == current_on:
                continue
            if tracker.last_command and now - tracker.last_command < settle:
                decision.reason = "stabilisation en cours"
                continue
            domain = config.entity_id.split(".", 1)[0]
            service = "turn_on" if decision.turn_on else "turn_off"
            if not self.hass.services.has_service(domain, service):
                decision.reason = f"service {domain}.{service} indisponible"
                continue
            _LOGGER.debug(
                "%s : %s (%s)", config.name, service, decision.reason
            )
            await self.hass.services.async_call(
                domain, service, {ATTR_ENTITY_ID: config.entity_id}, blocking=False
            )
            tracker.last_command = time.monotonic()
            tracker.last_command_wall = dt_util.utcnow().timestamp()

    # ---------------------------------------------------------------- persistance
    async def _save(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_save < SAVE_INTERVAL:
            return
        self._last_save = now
        await self._store.async_save(
            {
                "enabled": self.enabled,
                "overrides": {k: v.value for k, v in self.overrides.items()},
                "segments": {k: t.dump() for k, t in self.trackers.items()},
                "manual_until": {
                    k: t.manual_until for k, t in self.trackers.items() if t.manual_until
                },
            }
        )

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self.enabled = bool(stored.get("enabled", True))
        for key, value in (stored.get("overrides") or {}).items():
            if value in Override._value2member_map_:
                self.overrides[key] = Override(value)
        now = dt_util.utcnow().timestamp()
        for key, segments in (stored.get("segments") or {}).items():
            tracker = self.trackers.setdefault(key, RuntimeTracker())
            for segment in segments:
                start = float(segment[0])
                end = float(segment[1]) if len(segment) > 1 else 0.0
                if end == 0.0:
                    end = now
                tracker.segments.append([start, end])
            tracker.prune(now)
            tracker.manual_until = float((stored.get("manual_until") or {}).get(key, 0.0))

    async def async_shutdown(self) -> None:
        await self._save(force=True)
        await super().async_shutdown()
