// modules/setnav/setnav.controller — les réglages en onglets (RM3081) : une barre en haut, les cartes
// existantes réparties dessous, et le contenu d'un onglet chargé quand on l'ouvre — pas avant.
// Ouvrir les réglages n'interroge plus npm pour inventorier les moteurs quand on venait changer le thème.
//
// Les cartes hors onglet sont masquées par une CLASSE, jamais par `style.display` : l'authentification
// pilote déjà le `display` de ses deux cartes, et deux mains sur la même propriété finissent par se
// contredire. La classe dit « pas cet onglet », le style dit « rien à montrer » — deux questions
// différentes, deux mécanismes.
import { mount } from "../../core/dom.js";
import { SetnavViewModel, GROUPES } from "./SetnavViewModel.js";
import { SetnavBar } from "./Setnav.view.js";

const CLE = "karlSettingsTab";
const OFF = "setnav-off";

export function mountSetnav(el, ctx = {}) {
  const doc = ctx.document || (typeof document !== "undefined" ? document : null);
  const store = ctx.storage || (typeof localStorage !== "undefined" ? localStorage : { getItem() { return null; }, setItem() {} });
  /** Ce qu'il faut charger pour un onglet, par clé. Chaque chargeur n'est appelé qu'une fois. */
  const loaders = ctx.loaders || {};
  const faits = new Set();
  const state = { open: lu() };
  const h = mount(el, "", { events: [["click", "[data-action=\"settab\"]", (ev, n) => aller(n.dataset.tab, ev)]] });

  function lu() { try { return store.getItem(CLE) || GROUPES[0].key; } catch (e) { return GROUPES[0].key; } }
  function carte(id) { return doc && doc.getElementById ? doc.getElementById(id) : null; }
  /** Masquée par son propre module (droits, contexte) : l'onglet ne la ressuscite pas. */
  function masquee(id) {
    const n = carte(id);
    return !n || (n.style && n.style.display === "none");
  }
  function vides() { return GROUPES.filter(g => g.cards.every(masquee)).map(g => g.key); }
  function vm() { return new SetnavViewModel({ open: state.open, hidden: vides() }); }

  /** Montre les cartes de l'onglet courant, retire les autres de la vue. */
  function peindre() {
    const v = vm(), courant = v.courant;
    state.open = courant;
    for (const g of GROUPES) {
      for (const id of g.cards) {
        const n = carte(id);
        if (!n || !n.classList) continue;
        if (g.key === courant) n.classList.remove(OFF);
        else n.classList.add(OFF);
      }
    }
    h.update(SetnavBar(v));
  }

  async function charger(key) {
    if (!key || faits.has(key)) return;
    faits.add(key);
    const f = loaders[key];
    if (typeof f === "function") {
      try { await f(); } catch (e) { faits.delete(key); throw e; }
    }
  }

  async function aller(key, ev) {
    if (ev && ev.preventDefault) ev.preventDefault();
    // un onglet sans contenu n'est pas rendu : demander à l'ouvrir ne doit pas nous déplacer ailleurs
    if (!vm().onglets.some(t => t.key === key)) return;
    state.open = key;
    try { store.setItem(CLE, key); } catch (e) { /* stockage indisponible */ }
    peindre();
    await charger(state.open);
  }

  /** À l'ouverture du panneau : peindre, puis ne charger QUE l'onglet visible. */
  async function open() {
    peindre();
    await charger(state.open);
  }
  /** Une carte a été masquée ou révélée ailleurs (connexion, droits) : recalculer, sans rien charger. */
  function refresh() { peindre(); }
  return Object.assign(h, { open, aller, refresh, peindre, state, vm });
}
