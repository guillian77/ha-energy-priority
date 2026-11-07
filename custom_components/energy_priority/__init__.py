"""Intégration Energy Priority : gestion de priorités entre appareils."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PLATFORMS, VERSION
from .coordinator import EnergyPriorityCoordinator

_LOGGER = logging.getLogger(__name__)

CARD_URL = f"/{DOMAIN}/energy-priority-card.js"
_CARD_KEY = f"{DOMAIN}_card_registered"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Expose la carte Lovelace fournie par l'intégration (une seule fois)."""
    if hass.data.get(_CARD_KEY):
        return

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

    url = f"{CARD_URL}?v={VERSION}"
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, url)
        hass.data[_CARD_KEY] = True
        _LOGGER.debug("Carte Lovelace enregistrée via le frontend : %s", url)
    except Exception as err:  # pragma: no cover - frontend absent (tests)
        _LOGGER.debug("add_extra_js_url indisponible (%s), repli sur les ressources Lovelace", err)
        if _async_add_lovelace_resource(hass, url):
            hass.data[_CARD_KEY] = True


@callback
def _async_add_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """Repli : déclare la carte comme ressource Lovelace."""
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None:
            _LOGGER.warning(
                "Impossible d'enregistrer la carte Energy Priority : ajoute-la "
                "manuellement en ressource (%s) ou signale le problème.",
                url,
            )
            return False
        for item in resources.async_items():
            if str(item.get("url", "")).startswith(CARD_URL):
                return True
        hass.async_create_task(
            resources.async_create_item({"res_type": "module", "url": url})
        )
        return True
    except Exception as err:  # pragma: no cover
        _LOGGER.warning("Échec de l'enregistrement de la carte : %s", err)
        return False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Enregistre la carte Lovelace dès le chargement de l'intégration."""
    if hass.is_running:
        await _async_register_card(hass)
        return True

    async def _on_started(_event) -> None:
        await _async_register_card(hass)

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise une instance du contrôleur."""
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
