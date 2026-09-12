#!/usr/bin/env node
// Tests du panneau Supervision (RM3112) : une alerte sans client associé ne peut pas ouvrir de ticket et
// le dit ; une association proposée se distingue d'une association confirmée ; le cockpit n'invente
// jamais le client — il envoie celui que la proposition a donné et que l'humain a pu corriger.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const kids = {};
  const self = { id, style: {}, dataset: {}, value: "", kids,
    get innerHTML() { return inner; }, set innerHTML(v) { inner = v; },
    querySelector(s) { return kids[s] || null; }, querySelectorAll() { return []; }, contains: () => true,
    replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener() {},
    async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n };
      for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} });
      await settle(); } };
  return self; }

(async () => {
  const VM = await import(path.join(DIR, "src/modules/monitor/MonitorViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/monitor/Monitor.view.js"));
  const { mountMonitor } = await import(path.join(DIR, "src/modules/monitor/monitor.controller.js"));

  const data = { counts: { total: 3, grave: 1, sans_cible: 1 }, seuil_grave: 4, alerts: [
    { eventid: "1", name: "Disk space is low", severity: 4, severity_label: "élevé", since: "3 j",
      host: "srv-prd.abatik.com", host_name: "Abatik prod", grave: true, acknowledged: false,
      cible: { client: "abatik", project: "infra", source: "slug du client", confiance: 0.8 } },
    { eventid: "2", name: "swap", severity: 2, severity_label: "avertissement", since: "2 h",
      host: "inconnu.example", grave: false, cible: { client: "", project: "", source: "", confiance: 0 } },
    { eventid: "3", name: "mysql", severity: 1, severity_label: "information", since: "22 h",
      host: "srv.matnat.fr", grave: false,
      cible: { client: "matnat", project: "", source: "domaine", confiance: 0.6 } }] };

  // — ViewModel —
  const vm = new VM.MonitorViewModel({ data, seuil: 0 });
  const [a1, a2, a3] = vm.rows();
  assert(a1.ticketable && a1.cible === "abatik/infra", "un hôte associé à un client ET un projet peut ouvrir un ticket");
  assert(a1.devine && /slug/.test(a1.source), "une association proposée dit qu'elle l'est, et pourquoi");
  assert(!a2.ticketable && /aucun client/.test(a2.manque), "sans client, pas de ticket — et on dit pourquoi");
  assert(!a3.ticketable && /projet/.test(a3.manque), "client connu mais projet inconnu : on ne devine pas le projet");
  assert(a1.grave && a1.cls === "due" && a2.cls === "wait", "la gravité se voit dans la ligne");
  assert.strictEqual(vm.counts.sans_cible, 1);
  const conf = new VM.MonitorViewModel({ data: { alerts: [{ eventid: "9", name: "x", severity: 5, severity_label: "désastre", host: "h", cible: { client: "c", project: "p", confiance: 1, source: "confirmée" } }], counts: {} } });
  assert(!conf.rows()[0].devine, "une association confirmée n'est plus signalée comme devinée");
  console.log("✓ ViewModel : ce qui peut ouvrir un ticket, ce qui ne peut pas, et pourquoi");

  // — vue —
  const s = String(V.MonitorCard(vm));
  assert(!/\son\w+=/.test(s), "aucun on* dans la vue");
  assert(/data-action="ticket" data-id="1"/.test(s), "l'alerte située porte son bouton de ticket");
  assert(!/data-action="ticket" data-id="2"/.test(s), "l'alerte non située ne le porte PAS");
  assert(/data-action="page" data-page="hosts"/.test(s), "elle renvoie vers l'association à la place");
  assert(/srv-prd\.abatik\.com/.test(s) && /abatik\/infra/.test(s), "hôte et cible sont lisibles");
  const sh = String(V.MonitorCard(new VM.MonitorViewModel({ data, page: "hosts", hosts: {
    clients: ["abatik", "matnat"],
    hosts: [{ host: "srv-prd.abatik.com", name: "n", actif: true, cible: { client: "abatik", project: "infra", confiance: 1, source: "confirmée" } },
            { host: "x.example", name: "", actif: false, cible: { client: "", project: "", confiance: 0, source: "" } }] } })));
  assert(/data-action="assign-save"/.test(sh) && /data-action="assign-client"/.test(sh), "la page hôtes permet d'associer");
  assert(/désactivé/.test(sh), "un hôte désactivé se voit");
  console.log("✓ vue : bouton de ticket seulement là où il peut aboutir, page d'association");

  // — contrôleur —
  const el = fakeEl("monitorcard"); const envoyes = []; let confirme = true; const demandes = []; const tickets = [];
  const svc = { data, hosts: null, error: null,
    load: async () => data, loadHosts: async () => (svc.hosts = { clients: ["abatik"], hosts: [] }),
    assign: async (b) => { envoyes.push(["assign", b]); return { ok: true }; },
    ticket: async (b) => { envoyes.push(["ticket", b]); return { rm_id: 4242 }; } };
  const ctl = mountMonitor(el, { service: svc, notify: () => {}, confirm: (m) => { demandes.push(m); return confirme; },
    storage: { getItem: () => null, setItem: () => {} }, showTicket: (rm) => tickets.push(rm) });
  await ctl.open();

  await el.click("ticket", { id: "1" });
  assert(demandes[0].includes("abatik/infra") && demandes[0].includes("Disk space is low"),
         "la confirmation dit chez QUI et pour QUOI le ticket s'ouvre");
  const [kind, body] = envoyes[envoyes.length - 1];
  assert(kind === "ticket" && body.client === "abatik" && body.project === "infra",
         "le client et le projet partent tels que la proposition les a donnés");
  assert(body.host === "srv-prd.abatik.com" && body.name === "Disk space is low" && body.eventid === "1",
         "l'alerte part avec le ticket : sans elle, la description serait creuse");
  assert.deepStrictEqual(tickets, ["4242"], "la fiche du ticket créé s'ouvre");

  confirme = false; envoyes.length = 0;
  await el.click("ticket", { id: "1" });
  assert.strictEqual(envoyes.length, 0, "refus à la confirmation : aucun ticket créé");

  confirme = true;
  await el.click("ticket", { id: "2" });
  assert(envoyes.every(e => e[0] !== "ticket"), "une alerte sans client ne crée rien, même si on force le geste");

  await el.click("seuil", { seuil: "4" });
  assert.strictEqual(ctl.state.seuil, 4, "le seuil de gravité se change");
  console.log("✓ contrôleur : confirmation nommée, cible transmise sans invention, refus respecté");

  // RM3112 (retour de test) : le panneau est un tableau, pas un formulaire — il ne doit pas hériter
  // des 760 px qui obligent à défiler latéralement, au point de cacher la colonne du client.
  const css = fs.readFileSync(path.join(DIR, "src/modules/monitor/monitor.scss"), "utf8");
  assert(/#cp-monitor\s*\{[^}]*max-width:\s*none/.test(css), "le panneau supervision n'est pas bridé en largeur");
  assert(/table-layout:\s*fixed/.test(css) && /overflow-wrap:\s*anywhere/.test(css),
         "les colonnes sont pensées et le texte passe à la ligne au lieu de pousser la table");
  assert(/mon-hosts/.test(css) && /mon-hosts/.test(String(sh)), "la page hôtes a ses propres largeurs");

  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/id="monitorcard"/.test(html) && /data-arg="monitor"/.test(html), "le panneau a son hôte et son menu");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/mountMonitor\(/.test(boot) && /monitor:\s*\{/.test(boot), "il est monté et déclaré comme panneau");
  console.log("\nLe panneau Supervision passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
