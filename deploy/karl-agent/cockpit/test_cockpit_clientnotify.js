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
  async check(action, data, checked, value) { const n = { tagName: value === undefined ? "INPUT" : "SELECT", value: value === undefined ? "" : value, checked: checked !== false, dataset: Object.assign({ action }, data || {}), closest: () => n }; await self.fire("click", n); await self.fire("change", n); } };
  return self; }

(async () => {
  const S = await import(path.join(DIR, "src/modules/clientnotify/clientnotify.service.js"));
  const VM = await import(path.join(DIR, "src/modules/clientnotify/ClientNotifyViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/clientnotify/ClientNotify.view.js"));
  const { mountClientNotify } = await import(path.join(DIR, "src/modules/clientnotify/clientnotify.controller.js"));

  const DATA = () => ({ total: 4, clients: [
    { client: "clienta", label: "Clienta", count: 3, recipients: ["s@clienta.example", "m@ipro.fr"], orphans: [], projects: [
      { project: "prestashop", label: "Site PrestaShop", actif: true, tickets: [
        { id: 3025, title: "Paliers", url: "u/3025", queued_at: "2026-09-08T18:58" },
        { id: 2948, title: "Promotions", url: "u/2948", queued_at: "2026-09-08T18:58" }] },
      { project: "prestasync", label: "Synchro Dolibarr", actif: true, tickets: [
        { id: 3042, title: "Picking lots", url: "u/3042", queued_at: "2026-09-09T01:00" }] }] },
    { client: "cliente", label: "Cliente", count: 1, recipients: [], orphans: ["fantome"], projects: [
      { project: "site", label: "Site Cliente", actif: false, tickets: [{ id: 9001, title: "Autre", url: "", queued_at: "2026-09-01" }] }] },
  ] });

  // — service pur —
  assert.deepStrictEqual(S.idsOf(DATA(), "clienta"), ["3025", "2948", "3042"], "les ids d'un client, tous projets confondus");
  assert.deepStrictEqual(S.idsOf(DATA(), "inconnu"), [], "client inconnu : aucune sélection possible");
  assert.deepStrictEqual([...S.prune(new Set(["3025", "9999"]), ["3025", "2948"])], ["3025"], "un ticket sorti de la file sort de la sélection");

  // — menu —
  let m = new VM.ClientMenuViewModel({ clients: DATA().clients, total: 4 });
  assert.deepStrictEqual(m.items.map(i => i.text), ["Clienta (3)", "Cliente (1)"], "un client par ligne, avec son reste à annoncer");
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
    "Confirmer l'envoi à s@clienta.example, m@ipro.fr", "armé : le libellé dit à QUI ça part");
  assert(/écarter 1 ticket\(s\) sans notifier/.test(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), confirm: "dismiss" }).dismissLabel), "armé : dire que rien ne partira");
  r = new VM.ClientReportViewModel({ client: cal, sel: new Set() });
  assert(!r.canSend && !r.canDismiss && /Cochez/.test(r.why), "rien de coché : rien ne part, et on dit pourquoi");
  r = new VM.ClientReportViewModel({ client: DATA().clients[1], sel: new Set(["9001"]) });
  assert(!r.canSend && r.canDismiss && /Aucun destinataire/.test(r.why), "sans destinataire : envoi fermé, mise à l'écart possible");
  assert.deepStrictEqual(r.inactives, ["Site Cliente"], "projet dont l'option est coupée : dit, pas masqué");
  assert.deepStrictEqual(r.orphans, ["fantome"], "ref d'annuaire inconnue remontée");
  assert(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), busy: true }).canSend === false, "pendant l'envoi, plus de second clic");

  // — vues —
  const frag = String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), protocole: true, preview: { subject: "S", body: "B" } })));
  assert(!/\son\w+=/.test(frag), "aucun on* dans la vue");
  assert(/data-action="pick" data-rm="3025"/.test(frag) && /data-action="all"/.test(frag) && /data-action="proto"/.test(frag)
    && /data-action="send"/.test(frag) && /data-action="dismiss"/.test(frag), "tous les gestes en data-action");
  assert(/Aperçu de l'email/.test(frag) && /<pre class="cn-body">B<\/pre>/.test(frag), "l'aperçu est celui rendu par le serveur");
  // RM3052 : l'email part en HTML (le protocole de test est un tableau) — l'aperçu montre donc
  // l'email RENDU, dans une iframe cloisonnée : styles fidèles, rien qui s'exécute ni ne déteigne.
  const fragH = String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]),
    preview: { subject: "S", body: "texte", html: "<table><tr><td>A1</td></tr></table>" } })));
  assert(/<iframe class="cn-frame" sandbox="" /.test(fragH), "aperçu HTML : iframe cloisonnée (sandbox vide)");
  assert(/srcdoc="&lt;table&gt;/.test(fragH), "le HTML voyage ÉCHAPPÉ dans srcdoc (jamais injecté dans la page)");
  assert(!/<pre class="cn-body">/.test(fragH), "…et le repli texte ne double pas l'aperçu");
  assert(/<pre class="cn-body">/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]),
    preview: { subject: "S", body: "texte" } })))), "serveur sans HTML (ancienne version) : repli sur le texte, pas d'écran vide");
  assert(/disabled/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set() })))), "aucune case : boutons fermés");
  assert(/Aucune évolution en attente/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: { client: "x", projects: [] } })))), "client sans file : état vide explicite");
  assert(/Rien à annoncer/.test(String(V.ClientMenu(new VM.ClientMenuViewModel({ clients: [] })))), "menu vide explicite");
  assert(/data-action="client" data-client="clienta"/.test(String(V.ClientMenu(m = new VM.ClientMenuViewModel({ clients: DATA().clients, total: 4 })))), "chaque client est un geste");
  console.log("✓ compte-rendu client : menu compté, groupes par projet, sélection inter-projets, gardes d'envoi, vues sans on*");

  // — envoi de TEST (RM3052) : se relire dans une vraie boîte avant d'écrire au client —
  const vmT = new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]),
    contacts: [{ label: "Mathieu Moulin", email: "m@ipro.fr" }, { label: "Mathieu Moulin", email: "contact@ipro.fr" }],
    testTo: "m@ipro.fr" });
  assert.deepStrictEqual(vmT.contacts.map(c => c.email), ["m@ipro.fr", "contact@ipro.fr", "s@clienta.example"],
    "l'annuaire d'abord, puis les destinataires du client, sans doublon");
  assert(vmT.testValid && vmT.canTest, "adresse valide + sélection : le test est ouvert");
  assert(!new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), testTo: "pasunemail" }).testValid,
    "adresse invalide reconnue");
  assert(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), testTo: "pasunemail" }).canTest,
    "…mais le bouton reste CLIQUABLE : désactivé, il avalerait le premier clic après la frappe");
  assert(!new VM.ClientReportViewModel({ client: cal, sel: new Set(), testTo: "m@ipro.fr" }).canTest,
    "rien de coché : rien à tester non plus");
  const fragT = String(V.ClientReport(vmT));
  assert(/data-action="testpick"/.test(fragT) && /data-action="testto"/.test(fragT) && /data-action="test"/.test(fragT),
    "le bloc de test porte ses trois gestes : choisir, saisir, envoyer");
  assert(/<option value="m@ipro.fr" selected>/.test(fragT), "le contact courant est présélectionné");
  assert(/value="m@ipro.fr"/.test(fragT), "l'adresse saisie est conservée au repeint");

  // — RM3092 : prévenir aussi le DEMANDEUR, ticket par ticket —
  const vmD = new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025", "2948"]), dem: new Set(["3025"]) });
  assert.strictEqual(vmD.demCount, 1, "compte les demandeurs à prévenir");
  assert(!vmD.allDemOn, "…et sait que tous ne le sont pas");
  assert.strictEqual(new VM.ClientReportViewModel({ client: cal, sel: new Set(["3025"]), dem: new Set(["3025"]) }).allDemOn, true, "tous cochés");
  // un demandeur coché sur un ticket NON sélectionné ne compte pas : on n'écrit à personne
  // au sujet d'un ticket qui ne part pas.
  assert.strictEqual(new VM.ClientReportViewModel({ client: cal, sel: new Set(["2948"]), dem: new Set(["3025"]) }).demCount, 0,
    "demandeur d'un ticket décoché : ignoré");
  const fragD = String(V.ClientReport(vmD));
  assert(/data-action="pickdem" data-rm="3025"/.test(fragD), "une case demandeur par ligne");
  assert(/data-action="alldem"/.test(fragD), "…et une case pour toutes d'un coup");
  assert(/disabled/.test(String(V.ClientReport(new VM.ClientReportViewModel({ client: cal, sel: new Set(), dem: new Set() })))),
    "ligne non cochée : sa case demandeur est inactive");
  assert(/demandeur\(s\) seront prévenus séparément/.test(fragD), "l'écran dit ce qui va partir");

  // — contrôleur —
  const calls = []; let sendRes = { ok: true, sent: 2, to: ["s@clienta.example"] };
  let queue = DATA();
  const repo = {
    pending: async () => { calls.push("pending"); return queue; },
    preview: async (b) => { calls.push("preview:" + b.rm.join(",") + ":" + (b.protocole ? "p" : "-") + ":dem=" + ((b.requesters || []).join("|") || "-")); return { subject: "S" + b.rm.length, body: "corps" }; },
    send: async (b) => { calls.push("send:" + b.rm.join(",") + ":dem=" + ((b.requesters || []).join("|") || "-")); queue = { total: 1, clients: [Object.assign({}, DATA().clients[1])] }; return sendRes; },
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
  await ctl.open("clienta");
  assert(panels.length === 1 && ctl.count() === 3, "ouvrir un client : le panneau s'ouvre, TOUT est coché par défaut");
  assert(calls.some(c => c.startsWith("preview:3025,2948,3042:p")), "l'aperçu est demandé au serveur pour la sélection");
  assert(/Site PrestaShop/.test(el.innerHTML) && /RM3042/.test(el.innerHTML), "les deux projets du client sont rendus");

  await el.check("pick", { rm: "2948" });
  assert(ctl.count() === 2 && calls[calls.length - 1].startsWith("preview:3025,3042:p"), "décocher retire du lot et redemande l'aperçu");
  await el.click("all", { on: "0" });
  assert(ctl.count() === 0 && !svc.preview, "tout décocher : plus rien à envoyer, plus d'aperçu");
  await el.click("all", { on: "1" });
  assert(ctl.count() === 3, "tout cocher");
  await el.check("proto", {}, false);
  assert(store.m.karlCnProto === "0" && /:-:dem=/.test(calls[calls.length - 1]), "le protocole est un choix mémorisé, transmis au serveur");
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
  assert(calls.some(c => c.startsWith("send:2948,3042") && c.endsWith(":dem=-")), "aucun demandeur coché : aucun n'est prévenu");
  assert(toasts.some(t => /2 ticket\(s\) annoncés/.test(t)), "retour d'envoi affiché");
  assert(calls.filter(c => c === "pending").length >= 2 && badges[badges.length - 1] === "1", "la file est relue après envoi, le badge suit");

  queue = DATA(); await ctl.refresh(); await ctl.open("clienta");
  await el.click("all", { on: "0" }); await el.check("pick", { rm: "3042" });
  await el.click("dismiss"); assert(/Confirmer/.test(el.innerHTML), "écarter demande aussi confirmation");
  await el.click("dismiss");
  assert(calls.includes("dismiss:3042") && !calls.includes("send:3042"), "écarter n'envoie AUCUN email");
  assert(toasts.some(t => /aucun email/.test(t)), "…et le dit");

  // un serveur en échec ne doit pas laisser croire à un envoi
  repo.send = async () => { throw new Error("aucun destinataire résolu"); };
  queue = DATA(); await ctl.refresh(); await ctl.open("clienta");
  await el.click("send"); await el.click("send");
  assert(toasts.some(t => /envoi refusé : aucun destinataire résolu/.test(t)), "échec d'envoi : dit, jamais silencieux");
  assert(!ctl.state.busy, "…et le panneau redevient utilisable");

  // le test : il part où on l'envoie, et il ne touche à RIEN
  queue = DATA(); repo.send = async (b) => { calls.push("send:" + b.rm.join(",")); return sendRes; };
  await ctl.refresh(); await ctl.open("clienta");
  repo.test = async (b) => { calls.push("test:" + b.to.join(",") + ":" + b.rm.join(",")); return { ok: true, test: true, to: b.to }; };
  await el.click("test");
  assert(!calls.some(c => c.startsWith("test:")), "sans adresse : rien n'est envoyé");
  assert(toasts.some(t => /aucune adresse de test/.test(t)), "…et on dit pourquoi");
  await el.check("testto", {}, true, "pasunemail");
  await el.click("test");
  assert(!calls.some(c => c.startsWith("test:")) && toasts.some(t => /adresse de test invalide/.test(t)),
    "adresse invalide : refusée au clic, avec le texte fautif");
  await el.check("testto", {}, true, "moi@ipro.fr");
  const qBefore = calls.filter(c => c === "pending").length;
  await el.click("test");
  assert(calls.some(c => c === "test:moi@ipro.fr:3025,2948,3042"), "le test part à l'adresse saisie, avec la sélection exacte");
  assert(toasts.some(t => /test envoyé à moi@ipro.fr/.test(t)), "retour d'envoi de test");
  assert(calls.filter(c => c === "pending").length === qBefore, "un test NE relit pas la file : elle n'a pas bougé");
  assert(store.m.karlCnTestTo === "moi@ipro.fr", "l'adresse de test est mémorisée pour la prochaine fois");
  await el.check("testpick", {}, true, "s@clienta.example");
  assert(ctl.svc.testTo === "s@clienta.example", "choisir un contact remplit le champ");

  // la file injoignable : panneau vide mais honnête
  repo.pending = async () => { throw new Error("agent injoignable"); };
  await ctl.refresh();
  assert(toasts.some(t => /compte-rendu client : agent injoignable/.test(t)) && badges[badges.length - 1] === "", "file injoignable : signalée, badge éteint");
  ctl.unmount();
  console.log("✓ compte-rendu client (contrôleur) : tout coché à l'ouverture, aperçu suivi, envoi en deux temps, désarmement, file relue, échecs dits");
  console.log("\nLe panneau compte-rendu client passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
