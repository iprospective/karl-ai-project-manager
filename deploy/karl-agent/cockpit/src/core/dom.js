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
export function mount(el, frag, { events = [] } = {}) {
  if (!el) throw new Error("mount : élément hôte absent");
  const disposers = [];
  el.innerHTML = String(frag);

  for (const [type, selector, handler] of events) {
    disposers.push(on(el, type, selector, handler));
  }

  const handle = {
    el,
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
    update(next) { el.innerHTML = String(next); return handle; },
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
  };
  mounted.add(handle);
  return handle;
}

/** Ce qui est monté et ce que ça retient — pour la sonde mémoire (L1b). */
export function domStats() {
  let pending = 0;
  for (const h of mounted) pending += h.pending;
  return { mounted: mounted.size, pending };
}
