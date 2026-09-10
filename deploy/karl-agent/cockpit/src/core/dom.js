// core/dom — montage d'un fragment et CYCLE DE VIE. RM2889, lot L0.
//
// Le contrat tient en une phrase, et c'est la garde anti-fuite du chantier :
// **un `unmount()` libère tout ce que son `mount()` a créé.** Écouteurs,
// minuteries, abonnements au store, observateurs — rien ne survit au démontage.
//
// Corollaire de conception : plus de `onclick="..."` dans le HTML rendu. Les
// gestes passent par la délégation (`on`), donc par un écouteur POSÉ, donc par
// un écouteur qu'on peut RETIRER. C'est ce que le monolithe ne sait pas faire
// aujourd'hui, et c'est une piste sérieuse pour RM2807.
//
// Aucun accès au DOM à l'import : le module s'importe sous node nu (C5), les
// tests lui fournissent un document minimal.

const mounted = new Set();

/** RM3007 : le module d'un montage, lu dans la pile d'appel (`/src/modules/<domaine>/`), sans rien demander aux contrôleurs. */
export function moduleFromStack(stack) {
  const m = /\/src\/modules\/([^/]+)\//.exec(stack || "");
  if (m) return m[1];
  if (/\/src\/boot\.js/.test(stack || "")) return "boot";
  return "autre";
}
const callerModule = () => { try { return moduleFromStack(new Error().stack); } catch (e) { return "autre"; } };

/** Écouteur délégué : un seul écouteur sur la racine, quel que soit le nombre
 *  d'éléments. Retourne la fonction de retrait. */
export function on(root, type, selector, handler) {
  const listener = (ev) => {
    const el = ev.target && ev.target.closest ? ev.target.closest(selector) : null;
    if (el && (!root.contains || root.contains(el))) handler(ev, el);
  };
  root.addEventListener(type, listener);
  return () => root.removeEventListener(type, listener);
}

/**
 * Monte un fragment sûr dans un élément et rend une poignée.
 *
 * @param {Element} el     hôte du fragment
 * @param {object}  frag   valeur rendue par `html` (ou une chaîne déjà sûre)
 * @param {object}  opts   { events: [[type, selector, handler]…] }
 * @returns {{el, unmount(), track(fn), timer(fn, ms)}}
 */
export function mount(el, frag, { events = [], module = null } = {}) {
  if (!el) throw new Error("mount : élément hôte absent");
  const disposers = [];
  let renders = 1;
  el.innerHTML = String(frag);

  for (const [type, selector, handler] of events) {
    disposers.push(on(el, type, selector, handler));
  }

  const handle = {
    el,
    module: module || callerModule(),
    /** Enregistre une libération à jouer au démontage (abonnement, observateur…). */
    track(dispose) {
      if (typeof dispose !== "function") throw new Error("track attend une fonction");
      disposers.push(dispose);
      return dispose;
    },
    /** Minuterie répétée dont l'arrêt est garanti par le démontage. */
    timer(fn, ms) {
      const id = setInterval(fn, ms);
      disposers.push(() => clearInterval(id));
      return id;
    },
    /** Repeint le fragment SANS démonter : la délégation étant posée sur
     *  l'hôte, les écouteurs survivent et rien n'est à re-poser. */
    update(next) { el.innerHTML = String(next); renders++; return handle; },
    /** Libère tout, dans l'ordre inverse, puis vide l'hôte. */
    unmount() {
      while (disposers.length) {
        const dispose = disposers.pop();
        try { dispose(); }
        catch (err) { console.error("unmount : libération en erreur", err); }
      }
      el.innerHTML = "";
      mounted.delete(handle);
    },
    get pending() { return disposers.length; },
    /** RM3007 : rendus cumulés (montage + update) et nœuds actuellement sous l'hôte — lus par la sonde, jamais en continu. */
    get renders() { return renders; },
    get nodes() { try { return el.querySelectorAll ? el.querySelectorAll("*").length : 0; } catch (e) { return 0; } },
  };
  mounted.add(handle);
  return handle;
}

/**
 * RM3001 : écrire un fragment dans un sous-élément (options d'un select, badge, carte secondaire) — le SEUL point d'écriture HTML
 * hors `mount()`/`update()`. N'accepte qu'un fragment SÛR (`html\`…\``, `raw()`) ou le vide : une chaîne nue lève, c'est la garde
 * contre un attribut construit à la main. Rend l'élément (ou null s'il est absent : les hôtes optionnels restent optionnels).
 */
function safeHtml(frag, what) {
  if (frag == null || frag === "") return "";
  if (typeof frag === "object" && typeof frag.toString === "function" && frag.constructor && frag.constructor.name === "Safe") return String(frag);
  throw new Error(what + " : fragment non sûr — passer par html`…` ou raw()");
}
export function paint(el, frag) { if (!el) return null; el.innerHTML = safeHtml(frag, "paint"); return el; }
/** Ajoute un fragment sûr à la fin d'un élément (une option de plus dans un select) sans repeindre le reste. */
export function append(el, frag) { if (!el) return null; const h = safeHtml(frag, "append"); if (h) el.insertAdjacentHTML("beforeend", h); return el; }
/** RM3075 — symétrique d'`append` : insère EN TÊTE sans repeindre. Même contrôle d'échappement ;
 *  écrire du HTML brut reste interdit partout ailleurs (garde de test_cockpit_core). */
export function prepend(el, frag) { if (!el) return null; const h = safeHtml(frag, "prepend"); if (h) el.insertAdjacentHTML("afterbegin", h); return el; }

/** Ce qui est monté et ce que ça retient — pour la sonde mémoire (L1b). */
export function domStats() {
  let pending = 0;
  for (const h of mounted) pending += h.pending;
  return { mounted: mounted.size, pending };
}

/** RM3007 : la même chose, ventilée par module — pour la sonde mémoire (nœuds, écouteurs/minuteries/abonnements, rendus cumulés). */
export function domStatsByModule() {
  const out = {};
  for (const h of mounted) {
    const m = out[h.module] || (out[h.module] = { mounted: 0, pending: 0, nodes: 0, renders: 0 });
    m.mounted++; m.pending += h.pending; m.nodes += h.nodes; m.renders += h.renders;
  }
  return out;
}
