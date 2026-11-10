#!/usr/bin/env node
/**
 * Vérifie le rendu de la carte sans navigateur : node tests/test-carte.js
 *
 * La carte est un HTMLElement qui écrit dans shadowRoot.innerHTML. On fournit le
 * minimum (HTMLElement, customElements, window) puis on lui donne un état de
 * capteur, et on inspecte le HTML produit.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const SRC = path.join(__dirname, "..", "custom_components", "energy_priority", "www", "energy-priority-card.js");

let Carte = null;
global.HTMLElement = class {
  attachShadow() {
    this.shadowRoot = { innerHTML: "" };
    return this.shadowRoot;
  }
  addEventListener() {}
  dispatchEvent() {}
};
global.customElements = { define: (_nom, classe) => { Carte = classe; } };
global.CustomEvent = class { constructor(t, o) { this.type = t; Object.assign(this, o); } };
global.history = { pushState() {} };
global.window = {
  customCards: [],
  location: { href: "" },
  dispatchEvent() {},
};

new Function(fs.readFileSync(SRC, "utf8"))();
assert.ok(Carte, "la carte doit s'enregistrer via customElements.define");

function rendre(appareils) {
  const carte = new Carte();
  carte.setConfig({});
  carte.hass = {
    states: {
      "sensor.energy_priority_repartition": {
        state: "2200",
        last_updated: String(Date.now()),
        attributes: {
          solaire_w: 8, consommation_w: 2843, batterie_w: 0, batterie_soc: 95,
          heures_creuses: true, reseau_w: 2843, budget_w: 457,
          charge_de_base_w: 300, decharge_autorisee_w: 0,
          appareils,
        },
      },
    },
  };
  return carte.shadowRoot.innerHTML;
}

const cumulus = {
  cle: "cumulus", nom: "Cumulus", entite: "switch.cumulus", puissance: 2200,
  accordee: 2200, priorite: 7, etat: true, quota_h: 1.5, marche_24h_h: 2.0,
  mode: "auto", quota_restant_h: 0,
};

const htmlGrace = rendre([{ ...cumulus, raison: "grâce manuelle (12 min restantes)" }]);
assert.ok(htmlGrace.includes('class="why"'), "la ligne de motif doit être rendue");
assert.ok(htmlGrace.includes("grâce manuelle (12 min restantes)"),
  "le motif de la décision doit apparaître sur la carte");

const htmlAttente = rendre([{
  ...cumulus, accordee: 0, etat: false, priorite: 6, nom: "RadiateurSalon",
  raison: "puissance insuffisante (457 W disponibles)",
}]);
assert.ok(htmlAttente.includes("puissance insuffisante (457 W disponibles)"),
  "le motif doit aussi expliquer une mise en attente");

const htmlVide = rendre([{ ...cumulus, raison: "" }]);
assert.ok(!htmlVide.includes('class="why"'), "aucune ligne vide quand il n'y a pas de motif");

const htmlEchappe = rendre([{ ...cumulus, raison: '<script>alert("x")</script>' }]);
assert.ok(!htmlEchappe.includes("<script>"), "le motif est échappé avant injection");
assert.ok(htmlEchappe.includes("&lt;script&gt;"), "échappement attendu");

console.log("carte : 5 vérifications OK");
