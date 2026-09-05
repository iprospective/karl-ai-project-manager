#!/usr/bin/env node
// Tests de la coquille migrée (RM2889, L6) — le toast (RM2451 : avec action), les références cliquables (RM2585 titleLink, RM2596 linkify,
// RM2718 pastille, RM2623 glossaire ; capture au document, la tuile ne s'attache pas), le runner PM, l'attache/détache (RM2759/2816/2353/
// 2672/2466/2173/2330/2602/2673/1893/2283/2697 + raccourcis RM2330/2527) et les commandes statiques de la page (data-cmd).
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
function fakeEl(id) { const L = []; return { id, style: {}, className: "", textContent: "", offsetParent: {}, focused: 0, focus() { this.focused++; }, kids: [], appendChild(c) { this.kids.push(c); }, addEventListener(t, f, cap) { L.push([t, f, !!cap]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; }, get L() { return L; },
  async fire(type, ev) { for (const [t, f] of [...L]) if (t === type) await f(Object.assign({ preventDefault() { ev.prevented = true; }, stopPropagation() { ev.stopped = true; } }, ev || {})); } }; }
(async () => {
  const V = await import(path.join(DIR, "src/views/common/Links.view.js"));
  const { mountLinks } = await import(path.join(DIR, "src/controllers/links.controller.js"));
  const { mountNotify } = await import(path.join(DIR, "src/controllers/notify.controller.js"));
  const { PmService } = await import(path.join(DIR, "src/services/pm.service.js"));
  const { mountAttach } = await import(path.join(DIR, "src/controllers/attach.controller.js"));
  const { mountCommands } = await import(path.join(DIR, "src/controllers/commands.controller.js"));

  // — liens (vue) —
  let tl = V.titleLink("2585", "Mon <b>ticket</b>", "https://r.x");
  assert(/class="tlink"[^>]*data-link="ticket" data-rm="2585"/.test(tl) && /href="https:\/\/r\.x\/issues\/2585"/.test(tl) && /class="rmext"[^>]*data-link="ext"/.test(tl) && tl.includes("Mon &lt;b&gt;ticket&lt;/b&gt;") && !/<b>/.test(tl) && !/onclick/.test(tl), "RM2585 : titre → fiche (data-link), ↗ Redmine, échappé, aucun on*");
  assert.strictEqual(V.titleLink("chantier-x", "Truc", ""), "Truc", "slug → texte simple"); assert.strictEqual(V.titleLink(null, "x", ""), "x"); tl = V.titleLink("42", "T", ""); assert(/data-rm="42"/.test(tl) && !/rmext/.test(tl), "sans base Redmine : cliquable, pas de ↗");
  const lk = V.linkify("fix RM42 dans scripts/karl-agent.py cf https://x.io/p et <b>", (s) => s);
  assert(/class="olink"[^>]*data-link="ticket" data-rm="42">RM42</.test(lk) && /class="olink omono"[^>]*data-link="file" data-path="scripts\/karl-agent.py"/.test(lk) && /<a href="https:\/\/x.io\/p"/.test(lk) && !/<b>/.test(lk) && /&lt;b&gt;/.test(lk) && !/onclick/.test(lk), "RM2596 : RM → fiche, chemin → fichiers, URL → lien, reste échappé, aucun on*");
  assert.strictEqual(V.linkify("a RM1 b", (s) => s.toUpperCase()), 'A <span class="olink" title="Ouvrir la fiche RM1" data-link="ticket" data-rm="1">RM1</span> B', "RM2623 : le glossaire passe sur le texte échappé, pas sur les liens"); assert.strictEqual(V.linkify(null), "");
  assert(/pill warn">WIP</.test(V.markPillHtml("wip")) && /pill test">À TESTER</.test(V.markPillHtml("test")) && /pill ok">DONE</.test(V.markPillHtml("done")) && V.markPillHtml("test").endsWith("</span> "), "RM2718 : trois pastilles, espace de séparation");
  assert.strictEqual(V.markPillHtml(null), ""); assert.strictEqual(V.markPillHtml("zzz"), ""); assert.strictEqual(V.markPillHtml("constructor"), "", "une clé héritée d'Object ne produit rien");
  // — liens (contrôleur : capture au document, la tuile ne s'attache pas) —
  const doc = fakeEl("document"); const ev = [];
  const links = mountLinks(doc, { showTicket: (rm) => ev.push(["ticket", rm]), openFileRef: (p) => ev.push(["file", p]), glossify: (s) => s, redmineBase: () => "https://r.x" });
  assert(doc.L[0][2] === true, "l'écouteur est en phase de CAPTURE : il passe avant la tuile"); assert(/issues\/7/.test(links.titleLink("7", "t")) && /data-rm="9"/.test(links.linkify("RM9")) && links.markPillHtml("wip"));
  let e1 = { target: { closest: (sel) => sel === "[data-link]" ? { dataset: { link: "ticket", rm: "42" } } : null } }; await doc.fire("click", e1); assert(ev[0][0] === "ticket" && ev[0][1] === "42" && e1.stopped, "clic sur un titre : fiche ouverte, propagation coupée (la tuile ne s'attache pas)");
  e1 = { target: { closest: () => ({ dataset: { link: "file", path: "a/b.py" } }) } }; await doc.fire("click", e1); assert(ev[1][1] === "a/b.py"); e1 = { target: { closest: () => ({ dataset: { link: "ext" } }) } }; await doc.fire("click", e1); assert(e1.stopped && ev.length === 2, "↗ : le navigateur suit le lien, la tuile non");
  e1 = { target: { closest: () => null } }; await doc.fire("click", e1); assert(!e1.stopped, "un clic ordinaire n'est pas touché"); links.unmount(); assert.strictEqual(doc.listenerCount, 0);
  console.log("✓ liens (RM2585/2596/2718/2623) : vue sans on*, capture au document, propagation coupée");

  // — toast —
  const host = fakeEl("toast"); const timers = []; let cleared = 0;
  const notify = mountNotify(host, { later: (fn, ms) => { timers.push([fn, ms]); return timers.length; }, clear: () => cleared++, createEl: () => fakeEl("span") });
  notify.toast("ok"); assert(host.textContent === "ok" && host.className === "toast show" && timers[0][1] === 3200); notify.toast("aïe", true); assert(host.className === "toast show err" && cleared === 1, "un nouveau toast remplace le précédent"); timers[1][0](); assert.strictEqual(host.className, "toast");
  let undone = 0; notify.toastAction("⊖ retirée", "annuler", () => undone++); assert(host.textContent === "⊖ retirée  " && host.kids.length === 1 && host.kids[0].textContent === "annuler" && timers[2][1] === 8000, "RM2451 : toast avec action, 8 s"); await host.kids[0].fire("click", {}); assert(undone === 1 && host.className === "toast", "l'action referme le toast"); notify.unmount();
  console.log("✓ toast : simple, erreur, remplacé, avec action (RM2451)");

  // — runner PM —
  const calls = []; const caches = { resolveAt: { "42": 1, "7": 2 } }; const pm = new PmService({ repo: { async run(b) { calls.push(b); return { ok: 1 }; } }, caches });
  assert.deepStrictEqual(await pm.run("task-status", { rm_id: "42", statut: "en_cours" }, { confirm: true }), { ok: 1 }); assert.deepStrictEqual(calls[0], { name: "task-status", args: { rm_id: "42", statut: "en_cours" }, confirm: true }); assert(!("42" in caches.resolveAt) && "7" in caches.resolveAt, "le ticket touché est à re-résoudre, pas les autres");
  await pm.run("conso-report", {}); assert(!("confirm" in calls[1]) && "7" in caches.resolveAt); await pm.run("x", { rmId: "7" }); assert(!("7" in caches.resolveAt), "rmId aussi");
  console.log("✓ runner PM : commande, confirmation explicite, résolution invalidée");

  // — attache / détache —
  const placeholder = fakeEl("placeholder"), tabactions = fakeEl("tabactions"), reviewpane = fakeEl("reviewpane"), chipsrow = fakeEl("chipsrow"), composer = fakeEl("cmptext"), root = fakeEl("document");
  const log = []; const vis = new Set(["state", "files"]);
  const mk = (name, fns) => Object.fromEntries(fns.map(f => [f, (...a) => log.push(name + "." + f + (a.length ? "(" + a.join(",") + ")" : ""))]));
  const ctx = { center: mk("center", ["closeView", "closePanel", "title", "note"]), review: mk("review", ["yieldTo"]), project: mk("project", ["close"]), newticket: mk("newticket", ["close"]), terminal: mk("terminal", ["mountTerm", "unmountTerm"]),
    layout: Object.assign(mk("layout", ["showRight", "collapseRight", "switchPanel"]), { rightVisible: (t) => vis.has(t) }), meta: mk("meta", ["onAttach", "setTicket", "render"]), outline: mk("outline", ["reset", "load", "jumpUser", "scrollLive"]), worklog: mk("worklog", ["load"]), git: mk("git", ["reset", "refresh"]), files: mk("files", ["ensure", "reset"]), actions: mk("actions", ["renderChips"]), dashboard: mk("dashboard", ["refresh"]), refresh: mk("refresh", ["refreshSessions"]) };
  const att = mountAttach({ placeholder, tabactions, reviewpane, chipsrow, composer, root }, ctx);
  assert.strictEqual(att.current(), null); att.attach(42);
  assert.strictEqual(att.current(), "42", "l'attache est une chaîne"); assert(placeholder.style.display === "none" && tabactions.style.display === "", "le centre montre le terminal");
  assert.deepStrictEqual(log, ["center.closeView", "center.closePanel", "review.yieldTo", "project.close", "newticket.close", "terminal.mountTerm(42)", "layout.showRight", "meta.onAttach(42)", "outline.reset", "worklog.load", "git.reset", "files.ensure", "actions.renderChips", "layout.switchPanel(running)", "center.title", "center.note(session,42,RM42)", "refresh.refreshSessions"], "attacher : les vues cèdent la place, le terminal monte, les onglets visibles chargent, l'onglet est noté, la liste marque l'actif");
  log.length = 0; vis.add("outline"); vis.add("git"); vis.delete("state"); att.attach("slug"); assert(log.includes("outline.load") && log.includes("git.refresh") && !log.includes("worklog.load") && log.includes("center.note(session,slug,slug)"), "seuls les onglets visibles chargent ; un slug n'est pas préfixé RM");
  log.length = 0; att.reattach(); assert(log[5] === "terminal.mountTerm(slug)", "reattach = attach de la session courante");
  log.length = 0; att.detach(); assert.strictEqual(att.current(), null); assert(placeholder.style.display === "flex" && tabactions.style.display === "none" && reviewpane.style.display === "none" && chipsrow.style.display === "none");
  assert.deepStrictEqual(log, ["meta.setTicket()", "terminal.unmountTerm", "dashboard.refresh", "layout.collapseRight", "meta.render", "outline.reset", "files.reset", "files.ensure", "center.title"], "détacher : terminal démonté, tableau de bord, colonne repliée, encart vidé, fichiers repliés sur le projet");
  log.length = 0; att.reattach(); assert.strictEqual(log.length, 0, "rien d'attaché : reattach ne fait rien");
  // raccourcis clavier (RM2330 / RM2527) : seulement avec Alt, seulement attaché
  let k = { altKey: true, key: "ArrowUp" }; await root.fire("keydown", k); assert(log.length === 0 && !k.prevented, "détaché : les raccourcis dorment"); att.attach("1"); log.length = 0;
  k = { altKey: true, key: "ArrowUp" }; await root.fire("keydown", k); assert(log.includes("outline.jumpUser(-1)") && k.prevented); k = { altKey: true, key: "ArrowDown" }; await root.fire("keydown", k); assert(log.includes("outline.jumpUser(1)")); k = { altKey: true, key: "End" }; await root.fire("keydown", k); assert(log.includes("outline.scrollLive"));
  k = { altKey: true, key: "c" }; await root.fire("keydown", k); assert(composer.focused === 1 && k.prevented, "Alt+C : le composer prend le focus"); composer.offsetParent = null; k = { altKey: true, key: "C" }; await root.fire("keydown", k); assert(composer.focused === 1 && !k.prevented, "composer caché : rien");
  log.length = 0; k = { altKey: true, ctrlKey: true, key: "ArrowUp" }; await root.fire("keydown", k); k = { altKey: false, key: "ArrowUp" }; await root.fire("keydown", k); assert(log.length === 0, "Ctrl+Alt ou sans Alt : rien");
  att.unmount(); assert.strictEqual(root.listenerCount, 0);
  console.log("✓ attache / détache : orchestration des domaines dans l'ordre historique, raccourcis clavier");

  // — commandes statiques —
  const d2 = fakeEl("document"); const ran = [];
  const cmds = mountCommands(d2, { help: (arg) => ran.push(["help", arg]), nav: (arg) => ran.push(["nav", Number(arg)]), hist: () => ran.push(["hist"]) });
  let ce = { target: { closest: () => ({ dataset: { cmd: "help", arg: "tickets", stop: "" } }) } }; await d2.fire("click", ce); assert.deepStrictEqual(ran[0], ["help", "tickets"]); assert(ce.prevented && ce.stopped, "data-stop : le bouton d'aide ne replie pas la carte");
  ce = { target: { closest: () => ({ dataset: { cmd: "nav", arg: "-1" } }) } }; await d2.fire("click", ce); assert.deepStrictEqual(ran[1], ["nav", -1]); assert(!ce.prevented, "sans data-stop : geste ordinaire");
  ce = { target: { closest: () => ({ dataset: { cmd: "inconnu" } }) } }; await d2.fire("click", ce); assert.strictEqual(ran.length, 2, "commande inconnue : rien"); assert(cmds.has("hist") && !cmds.has("x")); cmds.run("hist"); assert.deepStrictEqual(ran[2], ["hist"]); cmds.unmount(); assert.strictEqual(d2.listenerCount, 0);
  console.log("✓ commandes statiques : délégation data-cmd, argument, data-stop");

  // — la page : chaque data-cmd de l'HTML a son geste dans boot.js ; les hôtes de l'attache existent —
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8"); const mapSrc = /mountCommands\(document, \{([\s\S]*?)\n\}\);/.exec(boot); assert(mapSrc, "carte des commandes introuvable dans boot.js");
  const known = new Set([...mapSrc[1].matchAll(/"([\w-]+)":/g)].map(m => m[1])); const used = [...new Set([...html.matchAll(/data-cmd="([\w-]+)"/g)].map(m => m[1]))];
  assert(used.length >= 12, "la page porte ses commandes en data-cmd (" + used.length + ")"); used.forEach(c => assert(known.has(c), "data-cmd sans geste dans boot.js : " + c));
  ["placeholder", "tabactions", "reviewpane", "chipsrow", "cmptext", "toast", "reattach"].forEach(id => assert(html.includes('id="' + id + '"'), "hôte manquant : " + id));
  assert(/mountAttach\(\{ placeholder: byId\("placeholder"\)/.test(boot) && /mountLinks\(document,/.test(boot) && /mountNotify\(byId\("toast"\)\)/.test(boot) && /new PmService\(\{ caches \}\)/.test(boot), "boot.js monte la coquille");
  console.log("✓ page : " + used.length + " commandes data-cmd toutes câblées, hôtes de l'attache en place");
  console.log("\nTous les tests de la coquille passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
