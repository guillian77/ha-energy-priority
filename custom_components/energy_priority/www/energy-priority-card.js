/**
 * Carte « Energy Priority » pour Home Assistant.
 *
 * Affiche en temps réel le budget disponible, les sources d'énergie et la
 * puissance accordée à chaque appareil piloté.
 *
 * Aucune dépendance externe : élément personnalisé natif, rendu auto-suffisant.
 */

const STYLE = `
  :host {
    display: block;
    --ep-solaire: #f59e0b;
    --ep-batterie: #34d399;
    --ep-reseau: #38bdf8;
    --ep-off: var(--disabled-text-color, #9aa4b2);
  }
  ha-card {
    padding: 16px 18px 14px;
    display: block;
  }
  .entete {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 2px;
  }
  .titre {
    font-size: 15px;
    font-weight: 600;
    color: var(--primary-text-color);
  }
  .hc {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: .4px;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(56, 189, 248, .16);
    color: var(--ep-reseau);
    text-transform: uppercase;
  }
  .budget {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 6px 0 10px;
  }
  .budget b {
    font-size: 30px;
    font-weight: 700;
    line-height: 1;
    color: var(--primary-text-color);
    white-space: nowrap;
    flex: 0 0 auto;
  }
  .budget .info {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.25;
  }
  .budget .info span {
    font-size: 12px;
    color: var(--secondary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .budget .info .force { color: #38bdf8; }

  .jauge {
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: var(--divider-color, rgba(255,255,255,.12));
    overflow: hidden;
    margin-bottom: 14px;
  }
  .jauge > i {
    position: absolute;
    inset: 0 auto 0 0;
    border-radius: 999px;
    background: linear-gradient(90deg, #f59e0b, #fbbf24);
    transition: width .4s ease;
  }
  .jauge.depasse > i {
    background: linear-gradient(90deg, #38bdf8, #0ea5e9);
  }

  .sources {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }
  .source {
    border: 1px solid var(--divider-color, rgba(255,255,255,.12));
    border-radius: 12px;
    padding: 8px 10px;
    min-width: 0;
  }
  .source .lbl {
    font-size: 11px;
    letter-spacing: .3px;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .source .val {
    font-size: 17px;
    font-weight: 650;
    color: var(--primary-text-color);
    margin-top: 2px;
    white-space: nowrap;
  }
  .source .sub { font-size: 11px; color: var(--secondary-text-color); }
  .pt { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; }
  .pt.solaire { background: var(--ep-solaire); }
  .pt.batterie { background: var(--ep-batterie); }
  .pt.reseau { background: var(--ep-reseau); }

  .liste-titre {
    font-size: 11px;
    letter-spacing: .8px;
    text-transform: uppercase;
    color: var(--secondary-text-color);
    margin: 0 0 6px 2px;
  }
  .appareil {
    display: grid;
    grid-template-columns: 26px 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 9px 10px;
    border-radius: 12px;
    margin-bottom: 6px;
    border: 1px solid transparent;
    background: var(--secondary-background-color, rgba(127,127,127,.07));
    transition: background .3s ease, border-color .3s ease;
  }
  .appareil.actif {
    border-color: rgba(245, 158, 11, .45);
    background: linear-gradient(90deg, rgba(245,158,11,.10), rgba(245,158,11,.02));
  }
  .prio {
    width: 24px; height: 24px;
    border-radius: 8px;
    display: grid; place-items: center;
    font-size: 12px; font-weight: 700;
    background: var(--divider-color, rgba(127,127,127,.25));
    color: var(--secondary-text-color);
  }
  .appareil.actif .prio { background: rgba(245,158,11,.22); color: #f59e0b; }
  .nom {
    font-size: 14px;
    font-weight: 550;
    color: var(--primary-text-color);
    display: flex; align-items: center; gap: 6px;
  }
  .det {
    font-size: 11.5px;
    color: var(--secondary-text-color);
    margin-top: 3px;
    display: flex; gap: 8px; flex-wrap: wrap;
  }
  .badge-mode {
    font-size: 10px; font-weight: 700; letter-spacing: .3px;
    padding: 1px 6px; border-radius: 6px;
    background: rgba(127,127,127,.2); color: var(--secondary-text-color);
    text-transform: uppercase;
  }
  .badge-mode.force { background: rgba(239,68,68,.18); color: #ef4444; }
  .barre {
    height: 4px; border-radius: 999px; margin-top: 6px;
    background: var(--divider-color, rgba(127,127,127,.2));
    overflow: hidden;
  }
  .barre > i {
    display: block; height: 100%; border-radius: 999px;
    background: linear-gradient(90deg, #f59e0b, #fbbf24);
    transition: width .4s ease;
  }
  .w {
    font-size: 14px; font-weight: 650; text-align: right;
    color: var(--primary-text-color); white-space: nowrap;
  }
  .w small { display: block; font-size: 11px; font-weight: 400; color: var(--secondary-text-color); }
  .vide, .erreur {
    font-size: 13px; color: var(--secondary-text-color); padding: 8px 2px;
  }
  .pied {
    font-size: 11px; color: var(--secondary-text-color);
    margin-top: 8px; display: flex; justify-content: space-between; gap: 8px;
  }
  @media (max-width: 380px) {
    .sources { grid-template-columns: 1fr 1fr; }
    .source:last-child { grid-column: span 2; }
  }
`;

const fmt = (v, unit = "") => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return `${Math.round(Number(v)).toLocaleString("fr-FR")}${unit ? " " + unit : ""}`;
};

class EnergyPriorityCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._dernier = null;
  }

  static getStubConfig() {
    return { entity: "sensor.energy_priority_repartition" };
  }

  setConfig(config) {
    this._config = config || {};
    this._dernier = null;
  }

  set hass(hass) {
    this._hass = hass;
    const etat = this._entite();
    if (!etat) {
      this._rendre(null);
      return;
    }
    if (this._dernier === etat.last_updated + "|" + etat.state) return;
    this._dernier = etat.last_updated + "|" + etat.state;
    this._rendre(etat);
  }

  getCardSize() {
    return 6;
  }

  _entite() {
    if (!this._hass) return null;
    if (this._config.entity) {
      return this._hass.states[this._config.entity] || null;
    }
    const trouve = Object.values(this._hass.states).find(
      (e) => e.attributes && Array.isArray(e.attributes.appareils)
    );
    return trouve || null;
  }

  _rendre(etat) {
    if (!this.shadowRoot) return;
    if (!etat) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>
        <div class="erreur">Entité de répartition introuvable — vérifie que l'intégration Energy Priority est chargée.</div>
      </ha-card>`;
      return;
    }

    const a = etat.attributes || {};
    const appareils = a.appareils || [];
    const solaire = a.solaire_w;
    const batterie = a.batterie_w;
    const soc = a.batterie_soc;
    const reseau = a.reseau_w;
    const budget = a.budget_w;
    const total = appareils.reduce((s, d) => s + (Number(d.accordee) || 0), 0);
    const reference = Math.max(Number(budget) || 0, total, 1);
    const pct = Math.min(100, Math.round((total / reference) * 100));
    const depasse = Number(budget) > 0 && total > Number(budget);

    const ligneSource = (cls, label, valeur, sous) => `
      <div class="source">
        <div class="lbl"><i class="pt ${cls}"></i>${label}</div>
        <div class="val">${valeur}</div>
        ${sous ? `<div class="sub">${sous}</div>` : ""}
      </div>`;

    const reseauTxt =
      reseau === null || reseau === undefined ? "—" : fmt(Math.abs(reseau), "W");
    const reseauSous =
      reseau === null || reseau === undefined
        ? ""
        : Number(reseau) >= 0
        ? "import"
        : "export";

    const batterieTxt =
      batterie === null || batterie === undefined ? "—" : fmt(batterie, "W");
    const batterieSous =
      soc === null || soc === undefined ? "SOC —" : `SOC ${Math.round(soc)} %`;

    const htmlAppareils = appareils
      .map((d) => {
        const accordee = Number(d.accordee) || 0;
        const nominale = Number(d.puissance) || 0;
        const part = nominale > 0 ? Math.min(100, Math.round((accordee / nominale) * 100)) : 0;
        const mode = d.mode && d.mode !== "auto"
          ? `<span class="badge-mode force">${d.mode === "force_on" ? "forcé ON" : "forcé OFF"}</span>`
          : "";
        const quota = Number(d.quota_h) > 0
          ? `quota ${Number(d.marche_24h_h).toFixed(1)}/${Number(d.quota_h)} h`
          : "";
        return `
          <div class="appareil ${d.etat ? "actif" : ""}">
            <div class="prio">${d.priorite}</div>
            <div>
              <div class="nom">${d.nom} ${mode}</div>
              <div class="det"><span>${fmt(nominale, "W")} nominal</span>${quota ? `<span>· ${quota}</span>` : ""}</div>
              <div class="barre"><i style="width:${part}%"></i></div>
            </div>
            <div class="w">${accordee > 0 ? fmt(accordee, "W") : "0 W"}<small>${d.etat ? "accordée" : "en attente"}</small></div>
          </div>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="entete">
          <span class="titre">Répartition de puissance</span>
          ${a.heures_creuses ? '<span class="hc">heures creuses</span>' : ""}
        </div>
        <div class="budget">
          <b>${fmt(total, "W")}</b>
          <div class="info">
            <span>accordés</span>
            <span class="${depasse ? "force" : ""}">budget ${budget === null || budget === undefined ? "—" : fmt(budget, "W")}</span>
          </div>
        </div>
        <div class="jauge ${depasse ? "depasse" : ""}"><i style="width:${pct}%"></i></div>

        <div class="sources">
          ${ligneSource("solaire", "Solaire", fmt(solaire, "W"), "")}
          ${ligneSource("batterie", "Batterie", batterieTxt, batterieSous)}
          ${ligneSource("reseau", "Réseau", reseauTxt, reseauSous)}
        </div>

        <div class="liste-titre">Appareils</div>
        ${htmlAppareils || '<div class="vide">Aucun appareil configuré.</div>'}

        <div class="pied">
          <span>Charge de base ${fmt(a.charge_de_base_w, "W")}</span>
          <span>Décharge autorisée ${fmt(a.decharge_autorisee_w, "W")}</span>
        </div>
      </ha-card>`;
  }
}

customElements.define("energy-priority-card", EnergyPriorityCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "energy-priority-card",
  name: "Energy Priority",
  description: "Puissance accordée en temps réel à chaque appareil",
  preview: false,
});
