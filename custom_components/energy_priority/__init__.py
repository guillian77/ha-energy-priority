"""Intégration Energy Priority : gestion de priorités entre appareils."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, VERSION
from .coordinator import EnergyPriorityCoordinator

_LOGGER = logging.getLogger(__name__)

CARD_URL = f"/{DOMAIN}/energy-priority-card.js"
_CARD_KEY = f"{DOMAIN}_card_registered"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Expose la carte Lovelace fournie par l'intégration (une seule fois)."""
    if hass.data.get(_CARD_KEY):
        return
    hass.data[_CARD_KEY] = True

    http = getattr(hass, "http", None)
    if http is not None:
        try:
            from homeassistant.components.http import StaticPathConfig

            await http.async_register_static_paths(
                [
                    StaticPathConfig(
                        f"/{DOMAIN}",
                        str(Path(__file__).parent / "www"),
                        cache_headers=False,
                    )
                ]
            )
        except Exception as err:  # pragma: no cover - dépend du contexte
            _LOGGER.debug("Chemin statique de la carte non enregistré : %s", err)

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    except Exception as err:  # pragma: no cover - frontend absent (tests)
        _LOGGER.debug("Carte Lovelace non enregistrée : %s", err)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise une instance du contrôleur."""
    if hass.is_running:
        await _async_register_card(hass)
    else:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            lambda _event: hass.async_create_task(_async_register_card(hass)),
        )

    coordinator = EnergyPriorityCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une instance."""
    coordinator: EnergyPriorityCoordinator = entry.runtime_data
    await coordinator.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Migration de %s depuis la version %s", DOMAIN, entry.version)
    return True
