"""Moteur de décision pur (sans dépendance Home Assistant).

Ce module contient toute la logique d'allocation de puissance. Il est
volontairement isolé pour pouvoir être testé sans instance Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Override(str, Enum):
    """Mode manuel d'un appareil."""

    AUTO = "auto"
    FORCE_ON = "force_on"
    FORCE_OFF = "force_off"


class DevicePhase(str, Enum):
    """État réel de l'entité contrôlée."""

    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


@dataclass
class DeviceConfig:
    """Configuration statique d'un appareil (saisie par l'utilisateur)."""

    key: str
    name: str
    entity_id: str
    power_w: float
    priority: int = 10  # plus petit = plus critique
    min_on_s: int = 60
    min_off_s: int = 60
    quota_h: float = 0.0  # 0 = quota désactivé
    hc_fallback: bool = True  # quota non atteint -> forçage en heures creuses


@dataclass
class DeviceSnapshot:
    """État dynamique d'un appareil à l'instant t."""

    phase: DevicePhase = DevicePhase.UNKNOWN
    on_duration_s: float = 0.0
    off_duration_s: float = 0.0
    runtime_24h_s: float = 0.0
    override: Override = Override.AUTO
    available: bool = True


@dataclass
class Settings:
    """Réglages globaux du contrôleur."""

    battery_charge_positive: bool = True
    battery_discharge_cap_w: float = 5000.0
    allow_battery_discharge: bool = True
    battery_use_cap: bool = False
    battery_soc_min: float = 20.0
    margin_w: float = 100.0
    hysteresis_w: float = 150.0
    grid_max_w: float | None = None
    fail_safe_all_off: bool = True
    hc_ignore_min_times: bool = True
    use_measured_grid: bool = False


@dataclass
class Inputs:
    """Valeurs lues sur les capteurs à l'instant t."""

    solar_w: float | None = None
    load_w: float | None = None
    battery_w: float | None = None
    battery_soc: float | None = None
    hc_active: bool = False
    grid_w: float | None = None  # positif = import, négatif = export


@dataclass
class Budget:
    """Résultat du calcul de puissance disponible."""

    valid: bool = False
    base_load_w: float = 0.0
    battery_discharge_w: float = 0.0
    available_w: float = 0.0
    grid_import_w: float = 0.0
    reason: str = ""


@dataclass
class Decision:
    """Décision pour un appareil."""

    key: str
    turn_on: bool
    reason: str
    deficit_s: float = 0.0


@dataclass
class Plan:
    """Plan complet renvoyé au coordinateur."""

    budget: Budget
    decisions: dict[str, Decision] = field(default_factory=dict)
    used_w: float = 0.0

    def reason(self, key: str) -> str:
        decision = self.decisions.get(key)
        return decision.reason if decision else "inconnu"


def battery_w_signed(inputs: Inputs, settings: Settings) -> float:
    """Puissance batterie signée : positif = décharge."""
    if inputs.battery_w is None:
        return 0.0
    return -inputs.battery_w if settings.battery_charge_positive else inputs.battery_w


def battery_discharge_w(inputs: Inputs, settings: Settings) -> float:
    """Puissance de décharge batterie utilisable (>= 0)."""
    if not settings.allow_battery_discharge:
        return 0.0
    if inputs.battery_soc is None or inputs.battery_soc < settings.battery_soc_min:
        return 0.0
    if settings.battery_use_cap:
        # Appoint restant sous le plafond : la décharge déjà en cours compte.
        measured = max(0.0, battery_w_signed(inputs, settings))
        return max(0.0, settings.battery_discharge_cap_w - measured)
    if inputs.battery_w is None:
        return 0.0
    discharge = (
        -inputs.battery_w if settings.battery_charge_positive else inputs.battery_w
    )
    return max(0.0, min(settings.battery_discharge_cap_w, discharge))


def compute_budget(
    inputs: Inputs,
    settings: Settings,
    on_power_w: float,
) -> Budget:
    """Calcule la puissance disponible pour les appareils pilotés.

    `on_power_w` est la puissance nominale cumulée des appareils pilotés
    actuellement allumés : elle est retirée de la consommation globale pour
    obtenir la charge de base, ce qui évite qu'un appareil que l'on allume
    fasse baisser le budget et déclenche une réaction en chaîne.
    """
    if inputs.solar_w is None or inputs.load_w is None:
        return Budget(valid=False, reason="capteur solaire ou consommation indisponible")

    base_load = max(0.0, inputs.load_w - on_power_w)
    discharge = battery_discharge_w(inputs, settings)

    if settings.use_measured_grid and inputs.grid_w is not None:
        # Le compteur réseau dit la vérité. On réintègre la puissance des
        # appareils pilotés déjà allumés : sans cela, leur propre coupure fait
        # apparaître un export artificiel et provoque un redémarrage immédiat.
        available = -inputs.grid_w + on_power_w - settings.margin_w
    else:
        available = inputs.solar_w + discharge - base_load - settings.margin_w

    # Import réseau réel : mesuré, pas estimé à partir de la décharge autorisée.
    if inputs.battery_w is None:
        signed_charge = 0.0
    else:
        signed_charge = (
            inputs.battery_w if settings.battery_charge_positive else -inputs.battery_w
        )
    grid_import = (
        inputs.grid_w
        if inputs.grid_w is not None
        else inputs.load_w - inputs.solar_w + signed_charge
    )
    return Budget(
        valid=True,
        base_load_w=round(base_load, 1),
        battery_discharge_w=round(discharge, 1),
        available_w=round(available, 1),
        grid_import_w=round(grid_import, 1),
        reason="ok",
    )


def _deficit_s(config: DeviceConfig, snapshot: DeviceSnapshot) -> float:
    """Temps de marche manquant pour atteindre le quota (secondes)."""
    if config.quota_h <= 0:
        return 0.0
    return max(0.0, config.quota_h * 3600.0 - snapshot.runtime_24h_s)


def build_plan(
    devices: list[tuple[DeviceConfig, DeviceSnapshot]],
    inputs: Inputs,
    settings: Settings,
    hc_boost_enabled: bool = True,
    now: float = 0.0,
) -> Plan:
    """Construit le plan d'allumage/extinction.

    En heures creuses, un appareil en retard de quota est servi en continu
    (sans rotation ni alternance) jusqu'à ce que son quota soit atteint ; les
    durées minimales de marche et d'arrêt sont alors ignorées par défaut, afin
    d'éviter les cycles marche/arrêt de quelques minutes.
    """
    usable = [(c, s) for c, s in devices if s.available]
    on_power = sum(c.power_w for c, s in usable if s.phase == DevicePhase.ON)
    budget = compute_budget(inputs, settings, on_power)
    plan = Plan(budget=budget)

    if not budget.valid:
        for config, snapshot in usable:
            if settings.fail_safe_all_off and snapshot.phase == DevicePhase.ON:
                plan.decisions[config.key] = Decision(
                    config.key, False, "capteurs indisponibles : arrêt de sécurité"
                )
            else:
                plan.decisions[config.key] = Decision(
                    config.key, snapshot.phase == DevicePhase.ON, "capteurs indisponibles"
                )
        return plan

    deficits = {config.key: _deficit_s(config, snapshot) for config, snapshot in usable}
    boosting: set[str] = set()
    if hc_boost_enabled and inputs.hc_active:
        for config, _snapshot in usable:
            if config.hc_fallback and deficits[config.key] > 0:
                boosting.add(config.key)

    ignore_min = settings.hc_ignore_min_times

    # 1. Appareils allumés : on garde les plus critiques tant que ça rentre.
    on_devices = [(c, s) for c, s in usable if s.phase == DevicePhase.ON]
    on_devices.sort(key=lambda item: (item[0].priority, item[1].runtime_24h_s))
    used = 0.0
    kept: set[str] = set()
    for config, snapshot in on_devices:
        deficit = deficits[config.key]
        if config.key in boosting:
            kept.add(config.key)
            used += config.power_w
            plan.decisions[config.key] = Decision(
                config.key,
                True,
                f"forçage heures creuses en cours, quota restant {deficit / 3600:.1f} h",
                deficit,
            )
        elif snapshot.on_duration_s < config.min_on_s:
            kept.add(config.key)
            used += config.power_w
            plan.decisions[config.key] = Decision(
                config.key,
                True,
                f"temps minimum de marche non atteint ({int(snapshot.on_duration_s)}s)",
                deficit,
            )
        elif used + config.power_w <= budget.available_w + settings.hysteresis_w:
            kept.add(config.key)
            used += config.power_w
            plan.decisions[config.key] = Decision(
                config.key, True, "puissance disponible suffisante", deficit
            )
        else:
            plan.decisions[config.key] = Decision(
                config.key,
                False,
                f"puissance insuffisante ({budget.available_w:.0f} W disponibles)",
                deficit,
            )

    # 2. Appareils éteints : candidats, triés par urgence de service.
    off_devices = [(c, s) for c, s in usable if s.phase != DevicePhase.ON]
    boosts: list[tuple[DeviceConfig, DeviceSnapshot, float]] = []
    normal: list[tuple[DeviceConfig, DeviceSnapshot]] = []
    for config, snapshot in off_devices:
        if config.key in boosting:
            boosts.append((config, snapshot, deficits[config.key]))
        else:
            normal.append((config, snapshot))

    boosts.sort(key=lambda item: item[2], reverse=True)
    if inputs.hc_active:
        # Pas de rotation en heures creuses : on solde les quotas par urgence.
        normal.sort(key=lambda item: (item[0].priority, -deficits[item[0].key], item[1].runtime_24h_s))
    else:
        normal.sort(key=lambda item: (item[0].priority, item[1].runtime_24h_s))

    def grid_ok(extra_w: float) -> bool:
        if settings.grid_max_w is None:
            return True
        estimate = max(0.0, budget.base_load_w + used + extra_w - inputs.solar_w)
        return estimate <= settings.grid_max_w

    # 2a. Forçage heures creuses : on passe outre le budget solaire.
    for config, snapshot, deficit in boosts:
        if snapshot.override == Override.FORCE_OFF:
            continue
        if snapshot.off_duration_s < config.min_off_s and not ignore_min:
            plan.decisions[config.key] = Decision(
                config.key,
                False,
                f"délai minimum d'arrêt en cours ({int(snapshot.off_duration_s)}s)",
                deficit,
            )
            continue
        if not grid_ok(config.power_w):
            plan.decisions[config.key] = Decision(
                config.key,
                False,
                "déclenchement heures creuses bloqué par la limite réseau",
                deficit,
            )
            continue
        used += config.power_w
        kept.add(config.key)
        plan.decisions[config.key] = Decision(
            config.key,
            True,
            f"forçage heures creuses, quota restant {deficit / 3600:.1f} h",
            deficit,
        )

    # 2b. Allocation classique dans la limite du budget.
    for config, snapshot in normal:
        deficit = deficits[config.key]
        if snapshot.off_duration_s < config.min_off_s:
            plan.decisions[config.key] = Decision(
                config.key,
                False,
                f"délai minimum d'arrêt en cours ({int(snapshot.off_duration_s)}s)",
                deficit,
            )
        elif used + config.power_w <= budget.available_w:
            used += config.power_w
            kept.add(config.key)
            plan.decisions[config.key] = Decision(
                config.key, True, "puissance disponible suffisante", deficit
            )
        else:
            plan.decisions[config.key] = Decision(
                config.key,
                False,
                f"puissance insuffisante ({budget.available_w:.0f} W disponibles)",
                deficit,
            )

    # 3. Priorité au mode manuel.
    for config, snapshot in usable:
        if snapshot.override == Override.FORCE_ON:
            plan.decisions[config.key] = Decision(config.key, True, "forçage manuel")
            if config.key not in kept:
                used += config.power_w
                kept.add(config.key)
        elif snapshot.override == Override.FORCE_OFF:
            plan.decisions[config.key] = Decision(config.key, False, "forçage manuel")
            if config.key in kept:
                kept.discard(config.key)
                used -= config.power_w

    plan.used_w = round(used, 1)
    return plan
