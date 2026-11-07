"""Vérifie l'enregistrement de la carte Lovelace."""

import sys
import types

from homeassistant.core import HomeAssistant

from custom_components.energy_priority import async_setup
from custom_components.energy_priority.const import DOMAIN


def _fake_frontend(monkeypatch, urls: set[str]) -> None:
    module = types.ModuleType("homeassistant.components.frontend")
    module.add_extra_js_url = lambda _hass, url: urls.add(url)
    monkeypatch.setitem(sys.modules, "homeassistant.components.frontend", module)


async def test_card_registered_at_startup(hass: HomeAssistant, monkeypatch) -> None:
    """Régression : le callback de démarrage créait une coroutine jamais attendue.

    La carte n'était alors jamais enregistrée, d'où « Custom element doesn't
    exist: energy-priority-card » dans le dashboard.
    """
    urls: set[str] = set()
    _fake_frontend(monkeypatch, urls)
    monkeypatch.setattr(
        HomeAssistant, "is_running", property(lambda self: False), raising=True
    )

    assert await async_setup(hass, {})
    assert not urls  # rien tant que HA n'a pas fini de démarrer

    hass.bus.async_fire("homeassistant_started")
    await hass.async_block_till_done()

    assert urls, "la carte doit être enregistrée au démarrage"
    url = next(iter(urls))
    assert url.startswith(f"/{DOMAIN}/") and "energy-priority-card.js" in url


async def test_card_registered_when_already_running(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Intégration ajoutée à chaud : enregistrement immédiat."""
    urls: set[str] = set()
    _fake_frontend(monkeypatch, urls)

    assert hass.is_running is True
    assert await async_setup(hass, {})
    await hass.async_block_till_done()

    assert any("energy-priority-card.js" in url for url in urls), urls
