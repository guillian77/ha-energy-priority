"""Vérifie que les libellés des sections sont bien résolus.

Régression : les champs placés dans une section doivent être traduits sous
`sections.<clé>.data.<champ>` ; un `data` à plat affiche les clés brutes.
"""

import pathlib
import shutil

from homeassistant.helpers import translation

SECTIONS = ("capteurs", "batterie", "budget", "heures_creuses", "securite")


async def test_section_translations_resolve(hass) -> None:
    source = pathlib.Path("custom_components").resolve()
    cible = pathlib.Path(hass.config.config_dir) / "custom_components"
    shutil.copytree(source, cible, dirs_exist_ok=True)

    for categorie, etape in (("config", "user"), ("options", "settings")):
        traductions = await translation.async_get_translations(
            hass, "fr", categorie, integrations={"energy_priority"}
        )
        for section in SECTIONS:
            prefixe = (
                f"component.energy_priority.{categorie}.step.{etape}"
                f".sections.{section}"
            )
            assert f"{prefixe}.name" in traductions, f"titre manquant : {prefixe}"
            champs = [
                cle for cle in traductions if cle.startswith(f"{prefixe}.data.")
            ]
            assert champs, f"libellés manquants : {prefixe}"
