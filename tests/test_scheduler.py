"""Tests du moteur de décision (exécutables sans Home Assistant)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from energy_priority.scheduler import (  # noqa: E402
    DeviceConfig,
    DevicePhase,
    DeviceSnapshot,
    Inputs,
    Override,
    Settings,
    build_plan,
    compute_budget,
)


def dev(key, power, priority=10, quota=0.0, hc_fallback=True, min_on=60, min_off=60):
    return DeviceConfig(
        key=key,
        name=key,
        entity_id=f"switch.{key}",
        power_w=power,
        priority=priority,
        min_on_s=min_on,
        min_off_s=min_off,
        quota_h=quota,
        hc_fallback=hc_fallback,
    )


def snap(phase=DevicePhase.OFF, on_s=9999, off_s=9999, runtime=0.0, override=Override.AUTO):
    return DeviceSnapshot(
        phase=phase,
        on_duration_s=on_s,
        off_duration_s=off_s,
        runtime_24h_s=runtime,
        override=override,
    )


class BudgetTests(unittest.TestCase):
    def test_base_load_excludes_controlled_devices(self):
        # 2000 W solaires, 1500 W de consommation dont 1000 W d'un appareil piloté
        inputs = Inputs(solar_w=2000, load_w=1500, battery_w=0, battery_soc=80)
        budget = compute_budget(inputs, Settings(margin_w=0), on_power_w=1000)
        self.assertTrue(budget.valid)
        self.assertEqual(budget.base_load_w, 500)
        self.assertEqual(budget.available_w, 1500)

    def test_battery_sign_charge_positive(self):
        settings = Settings(battery_charge_positive=True, margin_w=0, battery_soc_min=20)
        charging = Inputs(solar_w=1000, load_w=0, battery_w=800, battery_soc=50)
        self.assertEqual(compute_budget(charging, settings, 0).battery_discharge_w, 0)
        discharging = Inputs(solar_w=1000, load_w=0, battery_w=-800, battery_soc=50)
        self.assertEqual(compute_budget(discharging, settings, 0).battery_discharge_w, 800)

    def test_battery_sign_charge_negative(self):
        settings = Settings(battery_charge_positive=False, margin_w=0)
        charging = Inputs(solar_w=0, load_w=0, battery_w=-800, battery_soc=50)
        self.assertEqual(compute_budget(charging, settings, 0).battery_discharge_w, 0)
        discharging = Inputs(solar_w=0, load_w=0, battery_w=800, battery_soc=50)
        self.assertEqual(compute_budget(discharging, settings, 0).battery_discharge_w, 800)

    def test_grid_import_uses_measured_battery(self):
        # 1148 W solaires, 1519 W de consommation, batterie qui decharge 406 W
        settings = Settings(margin_w=100, battery_use_cap=True, battery_discharge_cap_w=1200)
        inputs = Inputs(solar_w=1148, load_w=1519, battery_w=-406, battery_soc=79)
        budget = compute_budget(inputs, settings, on_power_w=1194)
        # plafond 1200 dont 406 deja fournis par la batterie
        self.assertEqual(budget.battery_discharge_w, 794)
        self.assertEqual(budget.grid_import_w, -35)         # mais l'import reste reel

    def test_measured_grid_budget(self):
        # on importe 1027 W : plus rien de disponible malgre le solaire
        settings = Settings(margin_w=100, use_measured_grid=True, battery_use_cap=True,
                            battery_discharge_cap_w=1000)
        inputs = Inputs(solar_w=1817, load_w=3482, battery_w=-637, battery_soc=25,
                        grid_w=1027)
        budget = compute_budget(inputs, settings, on_power_w=2400)
        self.assertEqual(budget.battery_discharge_w, 363)
        self.assertEqual(budget.available_w, -1127)
        self.assertEqual(budget.grid_import_w, 1027)

    def test_measured_grid_budget_when_exporting(self):
        settings = Settings(margin_w=100, use_measured_grid=True)
        inputs = Inputs(solar_w=3000, load_w=1000, battery_w=0, battery_soc=80, grid_w=-1500)
        budget = compute_budget(inputs, settings, on_power_w=0)
        self.assertEqual(budget.available_w, 1400)

    def test_battery_soc_floor_blocks_discharge(self):
        settings = Settings(margin_w=0, battery_soc_min=30)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=-2000, battery_soc=25)
        self.assertEqual(compute_budget(inputs, settings, 0).battery_discharge_w, 0)

    def test_use_cap_allows_max_while_charging(self):
        # batterie en charge mais capable de fournir 1200 W a la demande
        settings = Settings(margin_w=0, battery_use_cap=True, battery_discharge_cap_w=1200)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=949, battery_soc=34)
        self.assertEqual(compute_budget(inputs, settings, 0).battery_discharge_w, 1200)

    def test_use_cap_respects_soc_floor(self):
        settings = Settings(margin_w=0, battery_use_cap=True, battery_soc_min=20)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=-500, battery_soc=15)
        self.assertEqual(compute_budget(inputs, settings, 0).battery_discharge_w, 0)

    def test_use_cap_off_by_default(self):
        settings = Settings(margin_w=0, battery_discharge_cap_w=1200)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=949, battery_soc=34)
        self.assertEqual(compute_budget(inputs, settings, 0).battery_discharge_w, 0)

    def test_discharge_cap(self):
        settings = Settings(margin_w=0, battery_discharge_cap_w=1500)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=-4000, battery_soc=80)
        self.assertEqual(compute_budget(inputs, settings, 0).battery_discharge_w, 1500)


class PriorityTests(unittest.TestCase):
    def test_priority_order(self):
        devices = [
            (dev("clim", 1000, priority=1), snap()),
            (dev("ballon", 2000, priority=2), snap()),
        ]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=2500, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim"].turn_on)
        self.assertFalse(plan.decisions["ballon"].turn_on)  # 1000 + 2000 > 2500

    def test_rotation_within_same_priority(self):
        # même priorité : l'appareil le moins servi sur 24 h passe d'abord
        devices = [
            (dev("clim_a", 1000, priority=1), snap(runtime=3600 * 6)),
            (dev("clim_b", 1000, priority=1), snap(runtime=3600 * 1)),
        ]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=1000, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim_b"].turn_on)
        self.assertFalse(plan.decisions["clim_a"].turn_on)

    def test_hysteresis_keeps_device_on(self):
        devices = [(dev("clim", 1000, priority=1), snap(DevicePhase.ON))]
        settings = Settings(margin_w=0, hysteresis_w=150)
        inputs = Inputs(solar_w=900, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim"].turn_on)  # 1000 <= 900 + 150

    def test_shutdown_when_budget_drops(self):
        devices = [(dev("clim", 1000, priority=1), snap(DevicePhase.ON))]
        settings = Settings(margin_w=0, hysteresis_w=150)
        inputs = Inputs(solar_w=500, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["clim"].turn_on)

    def test_min_on_time_protects_device(self):
        devices = [(dev("clim", 1000, priority=1, min_on=300), snap(DevicePhase.ON, on_s=100))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim"].turn_on)

    def test_min_off_time_blocks_restart(self):
        devices = [(dev("ballon", 1000, priority=1, min_off=300), snap(off_s=60))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=3000, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["ballon"].turn_on)


class QuotaTests(unittest.TestCase):
    def test_hc_boost_ignores_solar_budget(self):
        devices = [(dev("ballon", 2000, priority=5, quota=2.0), snap(runtime=0))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=0, battery_soc=80, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["ballon"].turn_on)
        self.assertIn("heures creuses", plan.decisions["ballon"].reason)

    def test_no_boost_outside_hc(self):
        devices = [(dev("ballon", 2000, priority=5, quota=2.0), snap(runtime=0))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=0, battery_soc=80, hc_active=False)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["ballon"].turn_on)

    def test_no_boost_when_quota_reached(self):
        devices = [(dev("ballon", 2000, priority=5, quota=2.0), snap(runtime=2 * 3600))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=0, battery_soc=80, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["ballon"].turn_on)

    def test_hc_boost_respects_grid_max(self):
        devices = [(dev("ballon", 3000, priority=5, quota=2.0), snap(runtime=0))]
        settings = Settings(margin_w=0, hysteresis_w=0, grid_max_w=3000)
        inputs = Inputs(solar_w=0, load_w=2000, battery_w=0, battery_soc=80, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["ballon"].turn_on)
        self.assertIn("limite réseau", plan.decisions["ballon"].reason)


class HcContinuousTests(unittest.TestCase):
    def test_boosting_device_stays_on_without_surplus(self):
        # nuit : 0 W solaire, l'appareil tourne deja, quota non atteint
        devices = [
            (dev("ballon", 2200, priority=2, quota=2.0, min_on=300),
             snap(DevicePhase.ON, on_s=1200, runtime=0.2 * 3600)),
        ]
        settings = Settings(margin_w=100, hysteresis_w=150)
        inputs = Inputs(solar_w=0, load_w=2500, battery_w=0, battery_soc=80, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["ballon"].turn_on)
        self.assertIn("heures creuses", plan.decisions["ballon"].reason)

    def test_boost_ignores_min_off_in_hc(self):
        devices = [
            (dev("ballon", 2200, priority=2, quota=2.0, min_off=600), snap(off_s=30, runtime=0)),
        ]
        settings = Settings(margin_w=100)
        inputs = Inputs(solar_w=0, load_w=500, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["ballon"].turn_on)

    def test_boost_respects_min_off_when_option_disabled(self):
        devices = [
            (dev("ballon", 2200, priority=2, quota=2.0, min_off=600), snap(off_s=30, runtime=0)),
        ]
        settings = Settings(margin_w=100, hc_ignore_min_times=False)
        inputs = Inputs(solar_w=0, load_w=500, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["ballon"].turn_on)

    def test_non_boosted_device_keeps_min_on_protection_in_hc(self):
        # appareil lance sur du surplus, min_on pas encore ecoule, pas de quota
        devices = [(dev("clim", 1200, priority=1, min_on=180), snap(DevicePhase.ON, on_s=60))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=1500, hc_active=True)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim"].turn_on)


class OverrideTests(unittest.TestCase):
    def test_force_on_ignores_budget(self):
        devices = [(dev("clim", 2000, priority=1), snap(override=Override.FORCE_ON))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=0, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertTrue(plan.decisions["clim"].turn_on)

    def test_force_off_wins(self):
        devices = [(dev("clim", 1000, priority=1), snap(DevicePhase.ON, override=Override.FORCE_OFF))]
        settings = Settings(margin_w=0, hysteresis_w=0)
        inputs = Inputs(solar_w=5000, load_w=0, battery_w=0, battery_soc=80)
        plan = build_plan(devices, inputs, settings)
        self.assertFalse(plan.decisions["clim"].turn_on)


class FailSafeTests(unittest.TestCase):
    def test_missing_sensor_turns_everything_off(self):
        devices = [(dev("clim", 1000), snap(DevicePhase.ON))]
        settings = Settings(fail_safe_all_off=True)
        plan = build_plan(devices, Inputs(solar_w=None, load_w=1000), settings)
        self.assertFalse(plan.decisions["clim"].turn_on)

    def test_missing_sensor_hold(self):
        devices = [(dev("clim", 1000), snap(DevicePhase.ON))]
        settings = Settings(fail_safe_all_off=False)
        plan = build_plan(devices, Inputs(solar_w=None, load_w=1000), settings)
        self.assertTrue(plan.decisions["clim"].turn_on)


if __name__ == "__main__":
    unittest.main(verbosity=2)
