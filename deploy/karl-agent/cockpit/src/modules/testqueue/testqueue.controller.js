// controllers/testqueue.controller — le panneau « à tester » : trois gestes. RM2889.
// Prêts du monolithe : le runner PM, la modale de capture, la résolution d'un ticket,
// la revue (ouverture, verdict), la marque d'épinglage, l'aide.
import { mount, paint as paintInto } from "../../core/dom.js";
import { TestQueueService } from "./testqueue.service.js";
import { TestQueueViewModel } from "./TestQueueViewModel.js";
import { TestQueuePanel } from "./TestQueue.view.js";
import { html } from "../../core/html.js";

export function mountTestQueue(el, ctx = {}) {
  // RM3131 : `el` accepte aussi `{ card, badge }` — le badge de l'onglet « à tester », posé à côté
  // de « en cours ». Forme historique (un élément nu) conservée : les appelants n'ont pas à bouger.
  const badge = (el && el.badge) || ctx.badge || null;
  el = (el && el.card) || el;
  const svc = ctx.service || new TestQueueService(undefined, ctx.run);
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const confirm = ctx.confirm || ((m) => window.confirm(m));
  const filters = { project: "", status: "", deployable: false, q: "", sort: "oldest" };
  const vm = () => new TestQueueViewModel({ all: svc.all, loaded: svc.loaded }, { filters, pin: ctx.pin });
  /** RM3131 : le compteur de l'onglet — le NOMBRE de tickets en attente de test, masqué à zéro.
   *  Un badge qui affiche « 0 » n'informe pas, il occupe : la file vide doit disparaître de l'œil. */
  function paintBadge(n) {
    if (!badge) return;
    badge.textContent = String(n || 0);
    badge.style.display = n ? "" : "none";
  }
  const paint = (opts) => {
    const m = vm();
    // Le badge compte TOUTE la file, pas la vue filtrée : il dit ce qui attend d'être testé,
    // pas ce que l'utilisateur a choisi d'afficher. Peint seulement une fois chargé — sinon il
    // annoncerait « 0 » pendant le chargement, ce qu'on lirait comme « rien à tester ».
    if (svc.loaded) paintBadge(m.all.length);
    return handle.update(TestQueuePanel(m, opts));
  };
  async function load() {
    paint({ loading: true });
    try { await svc.load(); if (ctx.afterLoad) ctx.afterLoad(); }
    catch (e) { notify(e.message, true); }
    paint();
  }
  const afterGesture = (rm) => (ctx.resolveRefresh ? Promise.resolve(ctx.resolveRefresh(rm)) : Promise.resolve()).then(load);
  async function envGesture(btn, busy, fn, rm) {
    btn.disabled = true; const old = btn.textContent; btn.textContent = busy;
    try { const r = await fn(); notify(r.message, !r.ok); if (r.title && ctx.capture && (r.out !== undefined)) ctx.capture(r.title, r.out); }
    finally { btn.disabled = false; btn.textContent = old; afterGesture(rm); }
  }
  const gestures = {
    help: () => ctx.help && ctx.help("tests"), refresh: () => load(), clear: () => { filters.q = ""; paint(); },
    review: (n) => ctx.openReview && ctx.openReview(n.dataset.rm),
    verdict: (n) => ctx.verdict && ctx.verdict(n.dataset.rm, n.dataset.kind, n),
    "cockpit-create": (n) => envGesture(n, "🚀 lancement…", () => svc.cockpitEnv(n.dataset.rm, "create"), n.dataset.rm),
    "cockpit-teardown": (n) => envGesture(n, "🧹 démontage…", () => svc.cockpitEnv(n.dataset.rm, "teardown"), n.dataset.rm),
    deploy: (n) => { const clone = confirm("Cloner la BDD pour cet env de test ?\nOK = clone dédié (" + n.dataset.rm + ") · Annuler = BDD partagée"); return envGesture(n, "🚀 déploiement…", () => svc.deploy(n.dataset.rm, clone), n.dataset.rm); },
    teardown: (n) => { if (!confirm("Démonter l'env de test de RM" + n.dataset.rm + " ? (branche et BDD partagée conservées)")) return; return envGesture(n, "🧹 démontage…", () => svc.teardown(n.dataset.rm), n.dataset.rm); },
  };
  const handle = mount(el, "", { events: [
    ["click", "[data-action]", (ev, n) => { const g = gestures[n.dataset.action]; if (g) return g(n); }],
    ["input", "[data-filter]", (ev, n) => { if (n.dataset.filter === "q") { filters.q = n.value || ""; const ul = handle.el.querySelector && handle.el.querySelector("#tq-list"); const cnt = handle.el.querySelector && handle.el.querySelector("#tq-count"); if (ul) { const v = vm(); paintInto(ul, v.items().length ? html`${v.items().map(i => TestQueuePanel.item(i))}` : html`<li style="color:var(--muted)">${v.emptyText}</li>`); if (cnt) cnt.textContent = v.count; } } }],
    ["change", "[data-filter]", (ev, n) => { const k = n.dataset.filter; filters[k] = n.type === "checkbox" ? !!n.checked : (n.value || ""); if (k !== "q") paint(); }],
  ] });
  paint();
  // les mêmes gestes, offerts à la revue qui les rend encore elle-même (ponts)
  return Object.assign(handle, { load, entry: (rm) => svc.entry(rm), loaded: () => svc.loaded, size: () => svc.all.length, filters,
    deploy: (rm, btn) => gestures.deploy(Object.assign(btn || {}, { dataset: { action: "deploy", rm: String(rm) } })),
    teardown: (rm, btn) => gestures.teardown(Object.assign(btn || {}, { dataset: { action: "teardown", rm: String(rm) } })),
    deployShared: (rm, btn) => { if (!confirm("Déployer la branche de RM" + rm + " dans l'env de test PARTAGÉ du projet ?\n(ressource commune — la branche qui y tourne sera remplacée ; refus automatique si travail non commité)")) return; return envGesture(btn || { dataset: {} }, "📤 déploiement…", () => svc.deployShared(rm), rm); } });
}
