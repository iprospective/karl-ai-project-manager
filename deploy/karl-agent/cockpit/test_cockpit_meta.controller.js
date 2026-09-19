#!/usr/bin/env node
// Tests de l'encart ℹ — CONTRÔLEUR (RM3021, scindé de test_cockpit_meta.js) : fiche depuis le cache puis fraîche, attache → ancrage, worklog
// source de tickets, fan-out borné (RM2807), gestes délégués, récap copié.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const { settle, fakeElement, JOURNAL, S, U, R } = require("./test_cockpit_meta.helpers.js");
(async () => {
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { MetaService } = await import(path.join(DIR, "src/modules/meta/meta.service.js"));
  const { mountMeta } = await import(path.join(DIR, "src/modules/meta/meta.controller.js"));

  // — le contrôleur —
  const infosEl = fakeElement(), ticketsEl = fakeElement(); const ev = []; let att = null; let wl = { rm_id: null, buckets: {} }, wlPending = null;
  const resolve = mkStore("r", { "42": R }); const inflight = {}; const usageCache = mkStore("usage");
  const T = { usageFresh: (s) => !!usageCache.get(s), usageInFlight: () => false, ensureUsage: async (s) => { ev.push(["usage", s]); usageCache.set(s, U); }, inFlight: (t) => !!inflight[t],
    ensureResolved: async (rm) => { ev.push(["resolve", rm]); inflight[rm] = true; await settle(); delete inflight[rm]; if (resolve.get(rm) === undefined) resolve.set(rm, { found: true, title: "T" + rm, status: "en_cours" }); return resolve.get(rm); }, revalidate: async () => {},
    // RM3140 : la liste d'une vue se résout en UNE requête — le faux dépôt journalise le LOT,
    // pas un événement par ticket : c'est la propriété qu'on veut tenir.
    ensureBriefs: async (ids) => { const lot = (ids || []).filter(t => resolve.get(t) === undefined);
      if (!lot.length) return null; ev.push(["briefs", lot.join(",")]); await settle();
      lot.forEach(t => resolve.set(t, { found: true, title: "T" + t, status: "en_cours", partial: true })); return null; } };
  const svc = new MetaService({ repo: { ws: {}, cards: {}, workspace(rm) { return this.ws[rm]; }, async refreshWorkspace(rm) { ev.push(["ws", rm]); this.ws[rm] = { is_git: true, branch: "b", clean: true }; return this.ws[rm]; }, projectCard(c, p, onLoad) { const k = c + "/" + p; if (this.cards[k] !== undefined) return this.cards[k]; this.cards[k] = null; ev.push(["card", k]); setTimeout(() => { this.cards[k] = { name: "Boutique" }; onLoad && onLoad(); }, 0); return null; } }, clipboard: { writeText: async (t) => ev.push(["clip", t.split("\n")[0]]) } });
  const ctr = mountMeta({ infos: infosEl, tickets: ticketsEl }, { ticket: T, service: svc, notify: (m, e) => ev.push(["toast", m, !!e]), md: (s) => s, ago: () => "1min", tipAttr: () => "",
    resolve: () => resolve, sess: () => mkStore("sess", { "42": S, calymix: { title: "calymix", registry: { branches: ["2661-x"] } } }), usage: () => usageCache, attached: () => att, worklog: () => wl, worklogPending: () => wlPending, loadWorklog: () => ev.push("loadWorklog"),
    showRight: (t) => ev.push(["right", t]), noteOpened: (id) => ev.push(["opened", id]), gotoTicket: (rm) => ev.push(["launcher", rm]), estimateTicket: (rm) => ev.push(["estimate", rm]), openReview: (rm) => ev.push(["review", rm]), reload: (rm) => ev.push(["reload", rm]), openStatusMenu: (rm, n, e) => ev.push(["status", rm, !!n]), reopen: (rm) => ev.push(["reopen", rm]), openProject: (k) => ev.push(["project", k]) });
  ctr.render(); assert(/attache une session pour voir ses infos/.test(infosEl.innerHTML) && /aucun ticket — attache une session/.test(ticketsEl.innerHTML), "rien d'attaché : deux messages, pas de requête"); assert(!ev.length);
  ctr.showTicket("RM42"); assert.deepStrictEqual(ev.slice(0, 2), [["opened", "42"], ["right", "tickets"]]); assert.strictEqual(ctr.current(), "42"); assert.strictEqual(ctr.facet(), "detail"); assert(/data-rm="42"[^>]*>RM42/.test(ticketsEl.innerHTML) && /Titre/.test(ticketsEl.innerHTML), "ticket ouvert hors session : affiché depuis le cache");
  assert(ev.some(x => x[0] === "ws" && x[1] === "42") && ev.some(x => x[0] === "card" && x[1] === "acme/shop"), "workspace et fiche projet demandés une fois"); await settle(); assert(/Boutique/.test(ticketsEl.innerHTML), "…et la fiche arrive dans le rendu");
  ev.length = 0; ctr.render(); assert(!ev.some(x => x[0] === "card") && !ev.some(x => x[0] === "ws"), "re-rendre ne redemande rien");
  // attache : l'ancrage devient le ticket affiché ; le worklog est demandé comme source de tickets
  att = "42"; ev.length = 0; ctr.onAttach("42"); assert.strictEqual(ctr.current(), "42"); assert(ev.includes("loadWorklog"), "RM2673 : le worklog est chargé sans attendre l'onglet état"); assert(ev.some(x => x[0] === "usage" && x[1] === "42"), "conso live demandée"); await settle();
  assert(/Sujet Redmine|Titre/.test(infosEl.innerHTML) && /karl-RM42/.test(infosEl.innerHTML) && /600 k/.test(infosEl.innerHTML), "infos : session + conso rendues"); ev.length = 0; ctr.render(); assert(!ev.some(x => x[0] === "usage"), "conso fraîche : pas redemandée");
  wl = { rm_id: "42", buckets: { todo: [{ ref: "RM2661" }] } }; ev.length = 0; ctr.renderTickets(); assert(!ev.includes("loadWorklog"), "worklog vu : plus de chargement"); assert.deepStrictEqual(ctr.sessionTickets(), ["42", "2726", "2661"]); assert(/data-rm="2726"/.test(ticketsEl.innerHTML) && /data-rm="2661"/.test(ticketsEl.innerHTML));
  // RM2807 : UN .then par ticket en vol — un second rendu pendant le vol ne ré-abonne pas
  const nResolve = ev.filter(x => x[0] === "resolve").length; ctr.renderTickets(); ctr.renderTickets(); assert.strictEqual(ev.filter(x => x[0] === "resolve").length, nResolve, "fan-out borné"); await settle(); assert(/T2726/.test(ticketsEl.innerHTML) || resolve.get("2726"), "les tickets en vol arrivent");
  // gestes
  ev.length = 0; await ticketsEl.click("tab", { rm: "2661" }); assert.strictEqual(ctr.current(), "2661"); await ticketsEl.click("facet", { facet: "conso" }); assert.strictEqual(ctr.facet(), "conso"); assert(/Aucune consommation/.test(ticketsEl.innerHTML) || /Consommation/.test(ticketsEl.innerHTML));
  await ticketsEl.click("facet", { facet: "workspace" }); await settle(); assert(/Workspace/.test(ticketsEl.innerHTML) && ev.some(x => x[0] === "ws" && x[1] === "2661"), "facette workspace : état demandé à l'ouverture");
  await ticketsEl.click("ticket", { rm: "42" }); assert.strictEqual(ctr.current(), "42"); assert.strictEqual(ctr.facet(), "detail", "un RM-id cliqué rouvre sur le détail");
  for (const [a, k] of [["launcher", "launcher"], ["estimate", "estimate"], ["review", "review"], ["reload", "reload"], ["reopen", "reopen"]]) { await ticketsEl.click(a, { rm: "42" }); assert(ev.some(x => x[0] === k && x[1] === "42"), "geste " + a); }
  await ticketsEl.click("status", { rm: "42" }); assert(ev.some(x => x[0] === "status" && x[1] === "42" && x[2] === true), "menu de statut ancré sur la pastille"); await ticketsEl.click("project", { key: "acme/shop" }); assert(ev.some(x => x[0] === "project" && x[1] === "acme/shop"), "🗂 fiche → surface projet (le showProject d'origine n'existait plus)");
  await infosEl.click("copy-infos", { rm: "42" }); await settle(); assert(ev.some(x => x[0] === "clip" && x[1] === "Session RM42") && ev.some(x => x[0] === "toast" && x[1] === "Récap copié"), "RM2611 : récap copié"); ev.length = 0; await infosEl.click("refresh-usage", { rm: "42" }); await settle(); assert(ev.some(x => x[0] === "usage"), "↻ force la conso");
  usageCache.invalidate("43"); const r43 = await svc.copyRecap(null); assert(!r43.ok && /pas encore chargées/.test(r43.message)); assert(/Presse-papier indisponible/.test((await new MetaService({ repo: svc.repo, clipboard: null }).copyRecap(["x"])).message));
  // la revue / la file disent quel ticket montrer, sans rendre ; détacher vide
  ctr.setTicket("77"); assert(ctr.ticketIs("77") && ctr.ticketIs(77) && !ctr.ticketIs("42") && ctr.facet() === "detail"); ctr.setTicket(null); assert.strictEqual(ctr.current(), null);
  att = null; ctr.render(); assert(/attache une session pour voir ses infos/.test(infosEl.innerHTML) && /aucun ticket — attache une session/.test(ticketsEl.innerHTML));
  ctr.unmount(); assert.strictEqual(infosEl.listenerCount + ticketsEl.listenerCount, 0); assert.strictEqual(infosEl.innerHTML, "");
  console.log("✓ contrôleur : fiche depuis le cache puis fraîche, attache → ancrage, worklog source, fan-out borné, gestes délégués, récap");
  console.log("\nTous les tests de l'encart ℹ passent.");
  console.log("\nTous les tests du contrôleur de l'encart passent.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
