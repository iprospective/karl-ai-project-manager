// modules/doc/helpspots.controller — pose les repères « ? » sur les zones du cockpit. RM3075.
//
// Trois contraintes ont dessiné ce contrôleur :
//   1. la moitié des zones sont RE-RENDUES à chaque tick (liste des sessions, worklog) : un repère
//      posé une fois disparaîtrait. D'où la ré-application, groupée et paresseuse ;
//   2. elle ne doit pas coûter à chaque frappe : un observateur par zone, et un délai qui absorbe
//      les rafales de rendu ;
//   3. rien ne doit être posé deux fois : `apply` est idempotent (un repère par zone, reconnu à son
//      attribut), et `clear` sait tout retirer quand la préférence s'éteint.
import { HELP_SPOTS, SPOT_ATTR, spotsEnabled, setSpotsEnabled, spotFrag, spotHost, spotById } from "./helpSpots.js";
import { append, prepend } from "../../core/dom.js";

export function mountHelpSpots(doc, ctx = {}) {
  const storage = ctx.storage || null;
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  let on = spotsEnabled(storage);
  let pending = null;
  const disposers = [];

  function clear() {
    for (const el of [...doc.querySelectorAll("[" + SPOT_ATTR + "]")]) el.remove();
  }

  /** Pose ce qui manque. Idempotent : une zone déjà repérée est laissée telle quelle. */
  function apply() {
    if (!on) return 0;
    let posed = 0;
    for (const spot of HELP_SPOTS) {
      const host = spotHost(doc, spot);
      if (!host || host.querySelector("[" + SPOT_ATTR + '="' + spot.id + '"]')) continue;
      (spot.where === "first" ? prepend : append)(host, spotFrag(spot));
      posed++;
    }
    return posed;
  }

  /** Groupe les rafales de rendu : dix mutations en 200 ms ne font qu'une passe. */
  function schedule() {
    if (pending) return;
    pending = later(() => { pending = null; apply(); }, 250);
  }

  function toggle(next) {
    on = setSpotsEnabled(storage, next);
    clear();
    if (on) apply();
    return on;
  }

  // Le clic : la page d'aide de la zone, à sa section quand elle en a une.
  const onClick = (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[" + SPOT_ATTR + "]") : null;
    if (!t) return;
    ev.preventDefault(); ev.stopPropagation();
    const spot = spotById(t.getAttribute(SPOT_ATTR));
    if (!spot || !ctx.openHelp) return;
    const p = ctx.openHelp(spot.topic);
    if (spot.anchor) {
      const go = () => scrollToAnchor(doc, spot.anchor);
      if (p && typeof p.then === "function") p.then(go, () => {}); else later(go, 60);
    }
  };
  if (doc.addEventListener) {
    doc.addEventListener("click", onClick, true);
    disposers.push(() => doc.removeEventListener("click", onClick, true));
  }

  // Les zones qui se re-rendent : un observateur sur leur conteneur, pas sur le document entier.
  const Obs = ctx.observer || (typeof MutationObserver !== "undefined" ? MutationObserver : null);
  if (Obs) {
    const roots = new Set();
    for (const spot of HELP_SPOTS) {
      const host = doc.querySelector(spot.sel);
      const root = host && host.parentElement ? host.parentElement : host;
      if (root) roots.add(root);
    }
    for (const root of roots) {
      const obs = new Obs(() => schedule());
      obs.observe(root, { childList: true, subtree: true });
      disposers.push(() => obs.disconnect());
    }
  }

  apply();
  return { apply, clear, toggle, enabled: () => on, refresh: schedule,
    unmount: () => { disposers.forEach(d => d()); clear(); } };
}

/** Fait défiler jusqu'au titre dont le texte porte `anchor`. Le markdown de l'aide n'a pas d'id sur
 *  ses titres : chercher le TEXTE évite d'inventer un schéma d'ancres qu'il faudrait maintenir des
 *  deux côtés (et qui se périmerait au premier renommage de section). */
export function scrollToAnchor(doc, anchor) {
  const want = norm(anchor);
  if (!want) return false;
  for (const h of [...doc.querySelectorAll(".helpbody h1, .helpbody h2, .helpbody h3, .helpbody h4")]) {
    if (norm(h.textContent).includes(want)) {
      if (h.scrollIntoView) h.scrollIntoView({ block: "start", behavior: "smooth" });
      return true;
    }
  }
  return false;
}

function norm(s) {
  return String(s == null ? "" : s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
}
