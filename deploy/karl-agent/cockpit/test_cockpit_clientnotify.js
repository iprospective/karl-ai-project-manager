#!/usr/bin/env node
// Tests du panneau « compte-rendu client » (RM3052) : menu des clients avec leur compte, page cochable en travers
// des projets, aperçu produit par le serveur, et les deux gestes irréversibles (envoyer, écarter) en deux temps.
//
// Ce qui est protégé ici tient en une phrase : **ce qui est coché est ce qui part**. Une sélection qui survit à un
// rafraîchissement, un envoi déclenché d'un seul clic, un aperçu décorrélé des cases — chacun enverrait un email
// faux à un client, et un email parti ne se rattrape pas.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, textContent: "", get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector() { return null; }, querySelectorAll() { return []; }, contains() { return true; }, appendChild() {}, remove() {}, addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
  async fire(type, node) { for (const [t, f] of [...L]) if (t === type) await f({ target: node, preventDefault() {}, stopPropagation() {} }, node); await settle(); },
  async click(action, data) { const n = { tagName: "BUTTON", dataset: Object.assign({ action }, data || {}), closest: () => n }; await self.fire("click", n); },
  async check(action, data, checked) { const n = { tagName: "INPUT", checked: checked !== false, dataset: Object.assign({ action }, data || {}), closest: () => n }; await self.fire("click", n); await self.fire("change", n); } };
  return self; }

(async () => {
  const S = await import(path.join(DIR, "src/modules/clientnotify/clientnotify.service.js"));
  const VM = await import(path.join(DIR, "src/modules/clientnotify/ClientNotifyViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/clientnotify/ClientNotify.view.js"));
  const { mountClientNotify } = await import(path.join(DIR, "src/modules/clientnotify/clientnotify.controller.js"));

  const DATA = () => ({ total: 4, clients: [
    { client: "calicote", label: "Calicote", count: 3, recipients: ["s@calicote.com", "m@ipro.fr"], orphans: [], projects: [
      { project: "prestashop", label: "Site PrestaShop", actif: true, tickets: [
        { id: 3025, title: "Paliers", url: "u/3025", queued_at: "2026-09-08T18:58" },
        { id: 2948, title: "Promotions", url: "u/2948", queued_at: "2026-09-08T18:58" }] },
      { project: "prestasync", label: "Synchro Dolibarr", actif: true, tickets: [
        { id: 3042, title: "Picking lots", url: "u/3042", queued_at: "2026-09-09T01:00" }] }] },
    { client: "abatik", label: "Abatik", count: 1, recipients: [], orphans: ["fantome"], projects: [
      { project: "site", label: "Site Abatik", actif: false, tickets: [{ id: 9001, title: "Autre", url: "", queued_at: "2026-09-01" }] }] },
  ] });

  // — service pur —
  assert.deepStrictEqual(S.idsOf(DATA(), "calicote"), ["3025", "2948", "3042"], "les ids d'un client, tous projets confondus");
  assert.deepStrictEqual(S.idsOf(DATA(), "inconnu"), [], "client inconnu : aucune sélection possible");
  assert.deepStrictEqual([...S.prune(new Set(["3025", "9999"]), ["3025", "2948"])], ["3025"], "un ticket sorti de la file sort de la sélection");

  // — menu —
  let m = new VM.ClientMenuViewModel({ clients: DATA().clients, total: 4 });
  assert.deepStrictEqual(m.items.map(i => i.text), ["Calicote (3)", "Abatik (1)"], "un client par ligne, avec son reste à annoncer");
  assert.strictEqual(m.badge, "4", "le badge porte le total");
  m = new VM.ClientMenuViewModel({ clients: [], total: 0 });
  assert(m.empty && m.badge === "", "rien à annoncer : pas de badge « 0 », pas de bruit");

  // — page client —
  const cal = DATA().clients[0];
  let r = new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025", "3042"]), protocole: true });
  assert.deepStrictEqual(r.groups.map(g => g.label), ["Site PrestaShop", "Synchro Dolibarr"], "tickets groupés par projet");
  assert.deepStrictEqual(r.groups[0].tickets.map(t => t.id + ":" + t.on), ["3025:true", "2948:false"], "les cases suivent la sélection");
  assert(r.count === 2 && r.total === 3 && !r.allOn, "compte des cochés / total");
  assert(r.multi, "sélection en travers de deux projets : signalée (un seul email partira)");
  assert(r.canSend && r.canDismiss && r.why === "", "destinataires + sélection : les deux gestes sont ouverts");
  assert.strictEqual(r.sendLabel, "✉ Envoyer (2)");
  assert.strictEqual(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), confirm: "send" }).sendLabel,
    "Confirmer l'envoi à s@calicote.com, m@ipro.fr", "armé : le libellé dit à QUI ça part");
  assert(/écarter 1 ticket\(s\) sans notifier/.test(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), confirm: "dismiss" }).dismissLabel), "armé : dire que rien ne partira");
  r = new VM.ClientReportViewModel({ client: cal, sel: new Set() });
  assert(!r.canSend && !r.canDismiss && /Cochez/.test(r.why), "rien de coché : rien ne part, et on dit pourquoi");
  r = new VM.ClientReportViewModel({ client: DATA().clients[1], sel: new Set(["9001"]) });
  assert(!r.canSend && r.canDismiss && /Aucun destinataire/.test(r.why), "sans destinataire : envoi fermé, mise à l'écart possible");
  assert.deepStrictEqual(r.inactives, ["Site Abatik"], "projet dont l'option est coupée : dit, pas masqué");
  assert.deepStrictEqual(r.orphans, ["fantome"], "ref d'annuaire inconnue remontée");
  assert(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), busy: true }).canSend === false, "pendant l'envoi, plus de second clic");

  // — vues —
  const frag = String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), protocole: true, preview: { subject: "S", body: "B" } })));
  assert(!/\son\w+=/.test(frag), "aucun on* dans la vue");
  assert(/data-action="pick" data-rm="3025"/.test(frag) && /data-action="all"/.test(frag) && /data-action="proto"/.test(frag)
    && /data-action="send"/.test(frag) && /data-action="dismiss"/.test(frag), "tous les gestes en data-action");
  assert(/Aperçu de l'email/.test(frag) && /<pre class="cn-body">B<\/pre>/.test(frag), "l'aperçu est celui rendu par le serveur");
  assert(/disabled/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set() })))), "aucune case : boutons fermés");
  assert(/Aucune évolution en attente/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: { client: "x", projects: [] } })))), "client sans file : état vide explicite");
  assert(/Rien à annoncer/.test(String(V.ClientMenu(new VM.ClientMenuViewModel({ clients: [] })))), "menu vide explicite");
  assert(/data-action="client" data-client="calicote"/.test(String(V.ClientMenu(m = new VM.ClientMenuViewModel({ clients: DATA().clients, total: 4 })))), "chaque client est un geste");
  console.log("✓ compte-rendu client : menu compté, groupes par projet, sélection inter-projets, gardes d'envoi, vues sans on*");

  // — contrôleur —
  const calls = []; let sendRes = { ok: true, sent: 2, to: ["s@calicote.com"] };
  let queue = DATA();
  const repo = {
    pending: async () => { calls.push("pending"); return queue; },
    preview: async (b) => { calls.push("preview:" + b.rm.join(",") + ":" + (b.protocole ? "p" : "-")); return { subject: "S" + b.rm.length, body: "corps" }; },
    send: async (b) => { calls.push("send:" + b.rm.join(",")); queue = { total: 1, clients: [Object.assign({}, DATA().clients[1])] }; return sendRes; },
    dismiss: async (b) => { calls.push("dismiss:" + b.rm.join(",")); queue = { total: 1, clients: [Object.assign({}, DATA().clients[1])] }; return { ok: true, dismissed: b.rm.length }; },
  };
  const store = { m: {}, getItem(k) { return this.m[k] || null; }, setItem(k, v) { this.m[k] = String(v); } };
  const svc = new S.ClientNotifyService({ repo, storage: store });
  const el = fakeEl("clientnotifycard"); const badges = [], toasts = []; const panels = [];
  // Les minuteries courtes (anti-rafale de l'aperçu) sont jouées tout de suite ; la longue (expiration de
  // l'armement) est CAPTURÉE, pour la déclencher à la main et vérifier qu'elle désarme.
  const longTimers = [];
  const ctl = mountClientNotify(el, { service: svc, storage: store, notify: (t) => toasts.push(t),
    badge: (t) => badges.push(t), openPanel: () => panels.push(1),
    later: (fn, ms) => { if (!ms || ms < 1000) fn(); else longTimers.push(fn); return 1; }, clear: () => {} });

  await ctl.refresh();
  assert.strictEqual(badges[badges.length - 1], "4", "le badge du bandeau porte le total en attente");
  await ctl.open("calicote");
  assert(panels.length === 1 && ctl.count() === 3, "ouvrir un client : le panneau s'ouvre, TOUT est coché par défaut");
  assert(calls.includes("preview:3025,2948,3042:p"), "l'aperçu est demandé au serveur pour la sélection");
  assert(/Site PrestaShop/.test(el.innerHTML) && /RM3042/.test(el.innerHTML), "les deux projets du client sont rendus");

  await el.check("pick", { rm: "2948" });
  assert(ctl.count() === 2 && calls[calls.length - 1] === "preview:3025,3042:p", "décocher retire du lot et redemande l'aperçu");
  await el.click("all", { on: "0" });
  assert(ctl.count() === 0 && !svc.preview, "tout décocher : plus rien à envoyer, plus d'aperçu");
  await el.click("all", { on: "1" });
  assert(ctl.count() === 3, "tout cocher");
  await el.check("proto", {}, false);
  assert(store.m.karlCnProto === "0" && calls[calls.length - 1].endsWith(":-"), "le protocole est un choix mémorisé, transmis au serveur");
  await el.check("proto", {}, true);

  const before = calls.filter(c => c.startsWith("send:")).length;
  await el.click("send");
  assert(calls.filter(c => c.startsWith("send:")).length === before, "premier clic : ARME, n'envoie pas");
  assert(/Confirmer l'envoi/.test(el.innerHTML), "…et le bouton dit ce qui va se passer");
  await el.check("pick", { rm: "3025" });
  assert(!/Confirmer l'envoi/.test(el.innerHTML), "changer la sélection DÉSARME (on ne confirme pas un autre lot)");
  await el.click("send");
  assert(/Confirmer l'envoi/.test(el.innerHTML), "réarmé");
  longTimers.pop()();   // 8 s plus tard, sans second clic
  assert(!/Confirmer l'envoi/.test(el.innerHTML), "un armement oublié EXPIRE : pas d'envoi au clic suivant");
  await el.click("send"); await el.click("send");
  assert(calls.some(c => c.startsWith("send:2948,3042")), "second clic : envoi de la sélection exacte");
  assert(toasts.some(t => /2 ticket\(s\) annoncés/.test(t)), "retour d'envoi affiché");
  assert(calls.filter(c => c === "pending").length >= 2 && badges[badges.length - 1] === "1", "la file est relue après envoi, le badge suit");

  queue = DATA(); await ctl.refresh(); await ctl.open("calicote");
  await el.click("all", { on: "0" }); await el.check("pick", { rm: "3042" });
  await el.click("dismiss"); assert(/Confirmer/.test(el.innerHTML), "écarter demande aussi confirmation");
  await el.click("dismiss");
  assert(calls.includes("dismiss:3042") && !calls.includes("send:3042"), "écarter n'envoie AUCUN email");
  assert(toasts.some(t => /aucun email/.test(t)), "…et le dit");

  // un serveur en échec ne doit pas laisser croire à un envoi
  repo.send = async () => { throw new Error("aucun destinataire résolu"); };
  queue = DATA(); await ctl.refresh(); await ctl.open("calicote");
  await el.click("send"); await el.click("send");
  assert(toasts.some(t => /envoi refusé : aucun destinataire résolu/.test(t)), "échec d'envoi : dit, jamais silencieux");
  assert(!ctl.state.busy, "…et le panneau redevient utilisable");

  // la file injoignable : panneau vide mais honnête
  repo.pending = async () => { throw new Error("agent injoignable"); };
  await ctl.refresh();
  assert(toasts.some(t => /compte-rendu client : agent injoignable/.test(t)) && badges[badges.length - 1] === "", "file injoignable : signalée, badge éteint");
  ctl.unmount();
  console.log("✓ compte-rendu client (contrôleur) : tout coché à l'ouverture, aperçu suivi, envoi en deux temps, désarmement, file relue, échecs dits");
  console.log("\nLe panneau compte-rendu client passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
