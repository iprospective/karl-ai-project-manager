#!/usr/bin/env node
// Tests de la disposition migrée (RM2889) — porte RM2466 volet 3 (colonnes repliables, onglets de droite), RM2579 (démarrage
// paramétrable, legacy meta → infos), RM2599 (largeur bornée, poignée, persistance), RM2952 (repli voulu, réinitialisation).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeEl(id, extra) { const L = []; const c = new Set(extra && extra.classes || []); const self = Object.assign({ id, dataset: {}, style: {}, checked: false, value: "", kids: [], classList: { toggle(k, on) { on ? c.add(k) : c.delete(k); }, contains(k) { return c.has(k); }, add(k) { c.add(k); } }, has: (k) => c.has(k),
  querySelectorAll(sel) { return self.kids.filter(k => sel === ".rnav button" ? k.dataset.rpanel !== undefined : k.rp); }, getBoundingClientRect: () => ({ right: 1000 }),
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, ev) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ preventDefault() {}, target: self }, ev || {})); } }, extra || {}); return self; }
(async () => {
  const M = await import(path.join(DIR, "src/modules/layout/panels.js"));
  const { LayoutService } = await import(path.join(DIR, "src/modules/layout/layout.service.js"));
  const { mountLayout } = await import(path.join(DIR, "src/modules/layout/layout.controller.js"));
  const R = M.rightPanelReduce, replie = { tab: "outline", collapsed: true, manual: false }, ouvert = { tab: "outline", collapsed: false, manual: false };
  assert.deepStrictEqual(R(replie, { type: "select", tab: "tickets" }), { tab: "tickets", collapsed: false, manual: false }); assert.deepStrictEqual(R(ouvert, { type: "select", tab: "tickets" }), { tab: "tickets", collapsed: false, manual: false }); assert.deepStrictEqual(R(ouvert, { type: "select", tab: "outline" }), { tab: "outline", collapsed: true, manual: true }, "re-sélectionner l'onglet actif replie");
  assert.deepStrictEqual(R(ouvert, { type: "show" }), ouvert); assert.deepStrictEqual(R({ tab: "outline", collapsed: true }, { type: "show" }), ouvert); assert.deepStrictEqual(R(ouvert, { type: "show", tab: "tickets" }), { tab: "tickets", collapsed: false, manual: false }); assert.deepStrictEqual(R({ tab: "tickets", collapsed: false }, { type: "collapse" }), { tab: "tickets", collapsed: true, manual: false }); assert.deepStrictEqual(R(replie, { type: "toggle" }), ouvert); assert.deepStrictEqual(R(ouvert, { type: "toggle" }), { tab: "outline", collapsed: true, manual: true });
  const voulu = { tab: "outline", collapsed: true, manual: true }; assert.deepStrictEqual(R(voulu, { type: "show" }), voulu, "RM2952 : un repli voulu tient tête à l'ouverture automatique"); assert.deepStrictEqual(R(voulu, { type: "show", tab: "tickets" }), { tab: "tickets", collapsed: false, manual: false }); assert.deepStrictEqual(R(voulu, { type: "toggle" }), { tab: "outline", collapsed: false, manual: false }); assert.deepStrictEqual(R(voulu, { type: "collapse" }), voulu); assert.deepStrictEqual(R(replie, { type: "show" }), ouvert);
  assert.deepStrictEqual(R(null, {}), { tab: "infos", collapsed: true, manual: false }); assert.deepStrictEqual(R({ tab: "meta", collapsed: false }, {}), { tab: "infos", collapsed: false, manual: false }, "legacy meta → infos"); assert.deepStrictEqual(R({ tab: "meta", collapsed: true }, { type: "show" }), { tab: "infos", collapsed: false, manual: false }); assert.deepStrictEqual(R({ tab: "zzz" }, {}), { tab: "infos", collapsed: true, manual: false }); assert.deepStrictEqual(R({ tab: "state", collapsed: false }, {}), { tab: "state", collapsed: false, manual: false }); assert.deepStrictEqual(R({ tab: "files", collapsed: false }, {}), { tab: "files", collapsed: false, manual: false }); assert.deepStrictEqual(R(replie, { type: "select", tab: "state" }), { tab: "state", collapsed: false, manual: false });
  assert.strictEqual(M.clampWidth(500), 500); assert.strictEqual(M.clampWidth(100), 240); assert.strictEqual(M.clampWidth(2000), 900); assert.strictEqual(M.clampWidth("abc"), 330); assert.strictEqual(M.defaultTabOf("outline"), "outline"); assert.strictEqual(M.defaultTabOf("files"), "infos", "l'onglet fichiers n'est pas proposé au démarrage"); assert.strictEqual(M.defaultTabOf(null), "infos"); assert.deepStrictEqual(M.TABS, ["state", "infos", "tickets", "files", "git", "projects", "outline"]);
  console.log("✓ modèle (RM2466/2579/2599/2952) : réducteur (select/show/toggle/collapse, repli voulu, legacy), largeur bornée, onglet de démarrage");
  const store = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
  const svc = new LayoutService({ storage: store }); assert(!svc.startOpen() && svc.defaultTab() === "infos" && !svc.leftCollapsed() && svc.width() === null, "défauts : repliée, infos, gauche ouverte, largeur CSS");
  svc.setStartOpen(true); svc.setDefaultTab("outline"); svc.saveLeft(true); svc.saveWidth(5000); assert(svc.startOpen() && svc.defaultTab() === "outline" && svc.leftCollapsed() && svc.width() === 900, "préférences persistées, largeur bornée"); svc.resetWidth(); assert.strictEqual(svc.width(), null); svc.saveRight({ tab: "git", collapsed: false, manual: false }); assert.strictEqual(store.d.karlRight, '{"tab":"git","collapsed":false,"manual":false}');
  assert.doesNotThrow(() => new LayoutService({ storage: { getItem() { throw new Error("privé"); }, setItem() { throw new Error("privé"); } } }).setStartOpen(true), "stockage refusé : silencieux");
  console.log("✓ service : préférences de ce navigateur, largeur bornée, stockage privé toléré");
  // — RM3003 : gabarit mobile — modèle —
  const MB = await import(path.join(DIR, "src/modules/layout/mobile.js"));
  assert.strictEqual(MB.detectLayout({ narrow: true }), "mobile"); assert.strictEqual(MB.detectLayout({ narrow: false }), "desktop"); assert.strictEqual(MB.detectLayout({ forced: "desktop", narrow: true }), "desktop"); assert.strictEqual(MB.detectLayout({ forced: "mobile", narrow: false }), "mobile"); assert.strictEqual(MB.detectLayout({ forced: "zz", narrow: true }), "mobile");
  assert.strictEqual(MB.forcedLayout("?a=1&layout=mobile", null), "mobile"); assert.strictEqual(MB.forcedLayout("?layout=desktop", "mobile"), "desktop", "l'URL gagne sur la préférence"); assert.strictEqual(MB.forcedLayout("", "mobile"), "mobile"); assert.strictEqual(MB.forcedLayout("?layout=géant", "zz"), null);
  assert.strictEqual(MB.pageOf("right"), "right"); assert.strictEqual(MB.pageOf("zz"), "left");
  const ni = MB.navItems("center", { attention: 2, attached: "42" }); assert.deepStrictEqual(ni.map(i => [i.page, i.active, i.badge, i.label]), [["left", false, "2", "panneaux"], ["center", true, "", "centre"], ["right", false, "", "session RM42"]]);
  assert.strictEqual(MB.navItems("left", { attention: 0, attached: "calymix" })[2].label, "session calymix"); assert.strictEqual(MB.navItems("left", {})[2].label, "détail"); assert.strictEqual(MB.navItems("left", {})[0].badge, "");
  const svc3 = new LayoutService({ storage: { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } } });
  assert.strictEqual(svc3.layoutPref(), null); svc3.setLayoutPref("mobile"); assert.strictEqual(svc3.layoutPref(), "mobile"); svc3.setLayoutPref("zz"); assert.strictEqual(svc3.layoutPref(), null);
  console.log("✓ gabarit mobile (RM3003) — modèle : détection (largeur, forçage URL/préférence), pages, barre du bas");
  const rpanel = fakeEl("rpanel", { classes: ["rpanel", "collapsed"] }), main = fakeEl("main"), rnav = fakeEl("rnav"), rtoggle = fakeEl("rtoggle"), ltoggle = fakeEl("ltoggle"), rhandle = fakeEl("rhandle"), startOpen = fakeEl("rp-startopen"), defTab = fakeEl("rp-deftab");
  const tabs = ["state", "infos", "tickets", "files", "git", "projects", "outline"]; rpanel.kids = tabs.map(t => fakeEl("b-" + t, { dataset: { rpanel: t } })).concat(tabs.map(t => fakeEl("rp-" + t, { rp: true })));
  const rootStyle = { vars: {}, setProperty(k, v) { this.vars[k] = v; }, removeProperty(k) { delete this.vars[k]; } }; const root = fakeEl("document", { documentElement: { style: rootStyle } }); global.getComputedStyle = () => ({ getPropertyValue: (k) => rootStyle.vars[k] || "" });
  const applied = []; let resized = 0; const st2 = { d: { karlRightDefaultTab: "outline", karlRightStartOpen: "1", karlLeftCollapsed: "1", karlRightWidth: "400" }, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
  const ctl = mountLayout({ main, rpanel, rnav, rtoggle, ltoggle, rhandle, startOpen, defTab }, { service: new LayoutService({ storage: st2 }), root, onApply: (r, visible) => applied.push([r.tab, r.collapsed, tabs.filter(visible).join(",")]), onResized: () => resized++ });
  ctl.restore(); assert.deepStrictEqual(ctl.right(), { tab: "outline", collapsed: false, manual: false }, "RM2579 : le démarrage suit les préférences (onglet par défaut, dépliée)"); assert(ctl.left() && main.has("lcollapsed") && !rpanel.has("collapsed") && rpanel.has("wide") && startOpen.checked === true && defTab.value === "outline" && rootStyle.vars["--rpanel-w"] === "400px", "…colonnes, classe wide (conversation), réglages, largeur restaurés");
  assert(rpanel.kids.find(k => k.id === "b-outline").has("active") && rpanel.kids.find(k => k.id === "rp-outline").has("active") && !rpanel.kids.find(k => k.id === "b-infos").has("active"), "l'onglet actif est marqué, son panneau aussi"); assert.deepStrictEqual(applied[applied.length - 1], ["outline", false, "outline"], "onApply dit ce qui est visible");
  await rnav.fire("click", { target: { closest: () => ({ dataset: { rpanel: "tickets" } }) } }); assert(ctl.rightVisible("tickets") && !ctl.rightVisible("outline") && !rpanel.has("wide")); await rnav.fire("click", { target: { closest: () => ({ dataset: { rpanel: "tickets" } }) } }); assert(rpanel.has("collapsed") && ctl.right().manual === true, "re-cliquer l'onglet actif replie, et c'est VOULU");
  ctl.showRight(); assert(rpanel.has("collapsed"), "RM2952 : l'attache (show contextuel) respecte le repli voulu"); ctl.showRight("files"); assert(ctl.rightVisible("files"), "…une demande ciblée déplie"); ctl.collapseRight(); assert(rpanel.has("collapsed") && ctl.right().manual === false); await rtoggle.fire("click"); assert(ctl.rightVisible("files"));
  await ltoggle.fire("click"); assert(!ctl.left() && !main.has("lcollapsed") && st2.d.karlLeftCollapsed === "0", "repli gauche mémorisé");
  await rhandle.fire("mousedown"); assert(ctl.state.resizing && rpanel.has("resizing")); await root.fire("mousemove", { clientX: 700 }); assert.strictEqual(rootStyle.vars["--rpanel-w"], "300px", "le panneau grandit vers la gauche (1000 − 700)"); await root.fire("mousemove", { clientX: 900 }); assert.strictEqual(rootStyle.vars["--rpanel-w"], "240px", "borné à 240"); await root.fire("mouseup"); assert(!ctl.state.resizing && !rpanel.has("resizing") && st2.d.karlRightWidth === "240" && resized === 1, "RM2599 : largeur persistée, terminal réajusté");
  await rhandle.fire("dblclick"); assert(rootStyle.vars["--rpanel-w"] === undefined && st2.d.karlRightWidth === undefined && resized === 2, "RM2952 : réinitialiser RETIRE la variable (le CSS retrouve 460 px sur la conversation)");
  ctl.collapseRight(); await rhandle.fire("mousedown"); assert(!ctl.state.resizing, "repliée : rien à redimensionner");
  await startOpen.fire("change", { target: { checked: false } }); await defTab.fire("change", { target: { value: "state" } }); assert(st2.d.karlRightStartOpen === "0" && st2.d.karlRightDefaultTab === "state", "réglages écrits au changement");
  ctl.unmount(); assert.strictEqual(rnav.listenerCount + rtoggle.listenerCount + ltoggle.listenerCount + rhandle.listenerCount + root.listenerCount + startOpen.listenerCount + defTab.listenerCount, 0);
  console.log("✓ contrôleur : restauration depuis les préférences, onglets, repli voulu, colonne gauche, poignée bornée + persistée, réinitialisation, réglages");
  // — RM2283/2760/2816 : panneaux commutables de la colonne gauche (migrés du monolithe, RM2889) —
  { const mk = (id, ds) => ({ id, dataset: ds || {}, cl: new Set(), classList: { toggle(c, v) { v ? this.owner.cl.add(c) : this.owner.cl.delete(c); } } }); const own = (o) => { o.classList.owner = o; return o; };
    const btns = ["running", "tickets", "projects"].map(n => own(mk("b-" + n, { panel: n }))), panels = ["running", "tickets", "projects"].map(n => own(mk("lp-" + n)));
    const L2 = []; const lnav = { querySelectorAll: () => btns, addEventListener(t, f) { L2.push([t, f]); }, removeEventListener(t, f) { const i = L2.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L2.splice(i, 1); } };
    const lbody = { querySelector: (sel) => panels.find(p => "#" + p.id === sel) || null, querySelectorAll: () => panels };
    const st2 = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
    const loads = []; const lay = mountLayout({ lnav, lbody }, { storage: st2, root: null, panelLoaders: { projects: () => loads.push("projects"), tickets: () => loads.push("tickets") } });
    assert.strictEqual(lay.switchPanel("projects"), "projects"); assert(btns[2].cl.has("active") && !btns[0].cl.has("active") && panels[2].cl.has("active") && st2.d.karlPanel === "projects" && loads.join() === "projects", "actif + persisté + chargé à la première activation");
    lay.switchPanel("running"); lay.switchPanel("projects"); assert.strictEqual(loads.join(), "projects", "le chargeur ne rejoue pas"); assert.strictEqual(lay.switchPanel("inconnu"), "running", "panneau inconnu → « en cours »"); assert.strictEqual(lay.panel(), "running");
    st2.d.karlPanel = "tickets"; assert.strictEqual(lay.restorePanel(), "tickets"); assert.deepStrictEqual(loads, ["projects", "tickets"]);
    for (const [t, f] of L2) if (t === "click") f({ target: { closest: () => btns[0] } }); assert(btns[0].cl.has("active") && lay.panel() === "running", "clic sur l'onglet : délégation par data-panel");
    lay.unmount(); assert.strictEqual(L2.length, 0);
    console.log("✓ panneaux gauche (RM2283/2760/2816) : actif persisté, chargeurs à la première activation, inconnu → en cours, clic délégué"); }
  console.log("\nTous les tests de la disposition passent.");

  // — RM3003 : gabarit mobile — contrôleur : media + mnav, pages, hooks du centre et de la droite —
  { const { mountLayout: ML } = await import(path.join(DIR, "src/modules/layout/layout.controller.js"));
    const mk = (id) => fakeEl(id, { dataset: {} }); const mainM = mk("main"), rpanelM = fakeEl("rpanel", { classes: ["rpanel", "collapsed"] }), rnavM = mk("rnav"), mnav = mk("mnav");
    let inner = ""; Object.defineProperty(mnav, "innerHTML", { get() { return inner; }, set(v) { inner = v; } });
    const media = { matches: true, L: [], addEventListener(t, f) { this.L.push([t, f]); }, removeEventListener(t, f) { this.L = this.L.filter(([a, b]) => !(a === t && b === f)); } };
    const rootM = { documentElement: { dataset: {}, style: { setProperty() {}, removeProperty() {} } }, addEventListener() {}, removeEventListener() {} };
    const layouts = []; let att = null;
    const stM = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
    const lay = ML({ main: mainM, rpanel: rpanelM, rnav: rnavM, mnav }, { storage: stM, root: rootM, media, search: "", attention: () => 3, attached: () => att, onLayout: (l) => layouts.push(l) });
    lay.restore();
    assert(lay.isMobile() && rootM.documentElement.dataset.layout === "mobile" && mainM.dataset.mpage === "left" && layouts.join() === "mobile", "écran étroit → gabarit mobile, page panneaux, onLayout prévenu");
    assert(/data-mpage="left"[^>]*class|class="mnav-btn active" data-mpage="left"/.test(inner) && /nbadge att">3</.test(inner) && /détail/.test(inner) && !/\son[a-z]+=/.test(inner), "barre du bas rendue : page active, badge des sessions en attente, aucun on*");
    assert.strictEqual(lay.centerShown(), "center"); assert.strictEqual(mainM.dataset.mpage, "center", "une vue ouverte au centre → page centre");
    lay.showRight("files"); assert(mainM.dataset.mpage === "right" && lay.rightVisible("files"), "un onglet de droite montré → page droite");
    lay.switchPanel("running"); assert.strictEqual(mainM.dataset.mpage, "left", "changer de panneau gauche → page panneaux");
    att = "42"; await mnav.fire("click", { target: { closest: () => ({ dataset: { mpage: "right" } }) } }); assert(mainM.dataset.mpage === "right" && /session RM42/.test(inner), "la barre du bas navigue et se repeint");
    assert.strictEqual(lay.mobileGo("zz"), "left", "page inconnue → panneaux");
    media.matches = false; media.L.find(([t]) => t === "change")[1](); assert(!lay.isMobile() && rootM.documentElement.dataset.layout === "desktop" && inner === "" && layouts.join() === "mobile,desktop", "écran élargi → bureau, barre vidée");
    assert.strictEqual(lay.mobileGo("right"), null, "au bureau, mobileGo est sans effet"); assert.strictEqual(lay.showRight("infos").tab, "infos");
    const lay2 = ML({ main: mk("main2"), mnav: mk("mnav2") }, { storage: stM, root: { documentElement: { dataset: {}, style: { setProperty() {}, removeProperty() {} } }, addEventListener() {}, removeEventListener() {} }, media: { matches: false }, search: "?layout=mobile" });
    lay2.restore(); assert(lay2.isMobile(), "?layout=mobile force le gabarit sur un grand écran");
    stM.setItem("karlLayout", "desktop"); const lay3 = ML({ main: mk("main3") }, { storage: stM, root: null, media: { matches: true }, search: "" }); lay3.restore(); assert(!lay3.isMobile(), "la préférence karlLayout=desktop gagne sur la largeur");
    lay.unmount(); assert.strictEqual(media.L.length, 0, "unmount retire l'écouteur de media query");
    console.log("✓ gabarit mobile (RM3003) — contrôleur : détection et bascule à chaud, pages, hooks centre/droite/panneaux, barre du bas, forçages"); }
  // — RM3051 : le split de la zone centrale — une OPTION, pas un fait acquis —
  //
  // Ce qu'on protège : par défaut, ouvrir un ticket ne doit PAS couper la zone centrale
  // (personne ne l'avait demandé) ; et quand on active le split, la session doit revenir
  // exactement dans l'état où elle était — un terminal déjà masqué reste masqué.
  { const { mountLayout: ML } = await import(path.join(DIR, "src/modules/layout/layout.controller.js"));
    const el = (id, display = "") => ({ id, style: { display }, classList: { c: {}, toggle(n, on) { this.c[n] = !!on; } }, getBoundingClientRect: () => ({ right: 0, bottom: 600 }), addEventListener() {}, removeEventListener() {}, querySelectorAll: () => [] });
    const st = { d: {}, getItem(k) { return this.d[k] === undefined ? null : this.d[k]; }, setItem(k, v) { this.d[k] = String(v); }, removeItem(k) { delete this.d[k]; } };
    const props = {}; const root = { documentElement: { dataset: {}, style: { setProperty(k, v) { props[k] = v; }, removeProperty(k) { delete props[k]; } } }, addEventListener() {}, removeEventListener() {} };
    const h = { reviewpane: el("reviewpane", "none"), viewpane: el("viewpane", "none"), panelpane: el("panelpane", "none"),
                centerhandle: el("centerhandle", "none"), termhost: el("termhost"), term: el("term", "none"), composer: el("composer"), main: el("main") };
    const L = ML(h, { storage: st, root, media: { matches: false }, search: "" });

    assert.strictEqual(L.centerSplit(), false, "défaut : PAS de split (l'option s'active exprès)");
    L.showCenter(true);
    assert(h.reviewpane.style.display === "" && h.termhost.style.display === "none" && h.composer.style.display === "none",
      "sans split : le ticket prend la zone, la session est masquée");
    assert.strictEqual(h.term.style.display, "none", "ce qui était DÉJÀ masqué le reste");
    assert.strictEqual(h.centerhandle.style.display, "none", "pas de poignée sans split");
    L.showCenter(false);
    assert(h.termhost.style.display === "" && h.composer.style.display === "" && h.reviewpane.style.display === "none",
      "à la fermeture, la session revient");
    assert.strictEqual(h.term.style.display, "none", "…et ce qui était masqué avant ne réapparaît pas");

    L.setCenterSplit(true);
    assert(L.centerSplit() && st.d.karlCenterSplit === "1", "l'option est mémorisée dans ce navigateur");
    L.showCenter(true);
    assert(h.termhost.style.display === "" && h.reviewpane.style.display === "" && h.centerhandle.style.display === "",
      "avec split : les deux cohabitent, la poignée apparaît");
    assert(h.reviewpane.classList.c.split === true, "le volet bas prend sa hauteur réglable");

    // bascule à CHAUD, ticket ouvert : la session doit revenir sans refermer le ticket
    L.setCenterSplit(false);
    assert(h.termhost.style.display === "none" && h.reviewpane.style.display === "" && h.centerhandle.style.display === "none",
      "désactiver le split pendant la consultation : la session se retire, le ticket reste");
    L.setCenterSplit(true);
    assert(h.termhost.style.display === "" && h.composer.style.display === "", "réactiver le rend à nouveau");

    // RM3115 : une VUE et un PANNEAU sont des surfaces centrales comme un ticket. Elles passaient par un
    // `display` brut : la session restait affichée et la page s'empilait SOUS le terminal et le composer.
    L.setCenterSplit(false);
    L.showCenter(false);
    L.showSurface("viewpane", true);
    assert(h.viewpane.style.display === "" && h.termhost.style.display === "none" && h.composer.style.display === "none",
      "une vue prend la zone, elle ne se met pas sous la session");
    L.showSurface("viewpane", false);
    assert(h.termhost.style.display === "" && h.composer.style.display === "", "en la fermant, la session revient");
    L.showSurface("panelpane", true);
    assert(h.panelpane.style.display === "" && h.termhost.style.display === "none",
      "un panneau non plus ne s'empile pas sous le terminal");

    // passer d'une surface à l'autre ne doit pas faire réapparaître la session entre les deux
    L.showSurface("viewpane", true);
    assert.strictEqual(h.termhost.style.display, "none", "deux surfaces ouvertes : la session reste masquée");
    L.showSurface("panelpane", false);
    assert.strictEqual(h.termhost.style.display, "none", "fermer l'une, l'autre restant ouverte : toujours masquée");
    L.showSurface("viewpane", false);
    assert(h.termhost.style.display === "" && h.composer.style.display === "",
      "la session ne revient qu'une fois la DERNIÈRE surface fermée");

    // hauteur : bornée, mémorisée, réinitialisable
    L.showCenter(true);
    h.centerhandle.style.display = "";
    L.state.center.resizing = true; L.state.center.bottom = 600;
    assert.strictEqual(typeof L.resetCenterH, "function");
    st.setItem("karlCenterH", "250"); L.applyCenter();
    assert.strictEqual(props["--reviewpane-h"], "250px", "la hauteur mémorisée est appliquée");
    st.setItem("karlCenterH", "5"); L.applyCenter();
    assert.strictEqual(props["--reviewpane-h"], "120px", "une hauteur aberrante est bornée (rien ne disparaît)");
    L.resetCenterH();
    assert(props["--reviewpane-h"] === undefined && st.d.karlCenterH === undefined, "double-clic : retour au défaut CSS");
    console.log("✓ split de la zone centrale (RM3051) : OFF par défaut, session masquée puis rendue à l'identique, bascule à chaud, hauteur bornée et mémorisée"); }
})().catch(e => { console.error("✗", e.message); process.exit(1); });