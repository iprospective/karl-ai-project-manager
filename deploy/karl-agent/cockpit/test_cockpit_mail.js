#!/usr/bin/env node
// Tests du domaine mail migré (RM2889, L1 — pilote). Sans navigateur, sans réseau.
//
// Porte les assertions historiques de test_cockpit.js sur renderMailList
// (RM2671) vers les cinq couches : les MÊMES garanties, mais chacune au bon
// étage — la dérivation dans le ViewModel, le balisage dans la vue, le geste
// dans le contrôleur avec un service factice.
// Lancer : node deploy/karl-agent/cockpit/test_cockpit_mail.js
"use strict";
const path = require("path");
const assert = require("assert");
const DIR = __dirname;

const mails = [
  { key: "aaa1", subject: "Panne de caisse", from_name: "CalyClay", from: "a@b.fr",
    date: "2026-08-17T09:00", folder: "INBOX.Clients", state: "à traiter", attachments: 2,
    routing: { client: "calyclay", project: null, source: "contacts", confidence: 0.8 } },
  { key: "bbb2", subject: "Re: suite", from: "c@d.fr", date: "2026-08-16T09:00",
    state: "créé", created_rm: 2710, rm_id: 2661, routing: {} },
  { key: "ccc3", subject: "Merci", from: "e@f.fr", date: "2026-08-15T09:00",
    state: "écarté", dismissed: { reason: "accusé de réception" }, routing: {} },
];
const opened = Object.assign({}, mails[0], {
  body: "Bonjour,\nça plante.", body_truncated: true,
  draft: { title: "Caisse HS", project: "calyclay/dolibarr", priority: "high",
           description: "Le TPE ne répond plus.", confidence: 0.75, actionable: true,
           warnings: ["projet hors liste (x) → écarté"] },
});

function fakeElement() {
  const listeners = []; let inner = "";
  const el = {
    get innerHTML() { return inner; }, set innerHTML(v) { inner = v; },
    contains: () => true,
    addEventListener(t, f) { listeners.push([t, f]); },
    removeEventListener(t, f) { const i = listeners.findIndex(([a, b]) => a === t && b === f); if (i >= 0) listeners.splice(i, 1); },
    querySelector(sel) { const m = new RegExp(`id="${sel.slice(1)}" value="([^"]*)"`).exec(inner); return m ? { value: m[1] } : null; },
    get listenerCount() { return listeners.length; },
    async click(action, key) {
      const btn = { dataset: { action }, disabled: false, closest: () => (key ? { dataset: { key } } : null) };
      const target = { closest: (s) => (s === "[data-action]" ? btn : null) };
      for (const [t, f] of [...listeners]) if (t === "click") await f({ type: "click", target });
    },
    async change(id, checked) {
      const box = { checked };
      const target = { closest: (s) => (s === "#" + id ? box : null) };
      for (const [t, f] of [...listeners]) if (t === "change") await f({ type: "change", target });
    },
  };
  return el;
}

(async () => {
  const { EmailFactory, routingTarget } = await import(path.join(DIR, "src/models/mail/Email.js"));
  const { EmailViewModel } = await import(path.join(DIR, "src/viewmodels/mail/EmailViewModel.js"));
  const { MailList, MailPanel } = await import(path.join(DIR, "src/views/mail/MailPanel.view.js"));
  const { MailService } = await import(path.join(DIR, "src/services/mail.service.js"));
  const { mountMailPanel } = await import(path.join(DIR, "src/controllers/mail.controller.js"));

  // — modèle : invariants et dérivations, sans HTML —
  assert.throws(() => EmailFactory.one({ subject: "sans clé" }), /champs manquants key/);
  const es = EmailFactory.many(mails);
  assert.strictEqual(routingTarget(es[0]), "calyclay/?", "client sans projet doit rester « /? » (pas de choix silencieux)");
  assert.strictEqual(routingTarget(es[1]), "à classer");
  assert.deepStrictEqual(es[1].routing, {}); assert.strictEqual(es[1].attachments, 0);
  console.log("✓ modèle : factory (clé requise, défauts), cible de routage");

  // — ViewModel : ce qu'on montre, décidé sans une balise —
  const vm0 = new EmailViewModel(es[0], {});
  assert.strictEqual(vm0.confidence, "80%"); assert.strictEqual(vm0.source, "contacts");
  assert.strictEqual(vm0.badge, "•"); assert(!vm0.open); assert(!vm0.hasDraft);
  const vmo = new EmailViewModel(EmailFactory.one(opened), { openKey: "aaa1" });
  assert(vmo.open && vmo.hasDraft); assert.strictEqual(vmo.draftProject, "calyclay/dolibarr");
  assert.strictEqual(vmo.draftPriority, "high"); assert.strictEqual(vmo.draftConfidence, "75%");
  assert.deepStrictEqual(vmo.actions().map(a => a.id), ["center", "draft", "create", "note", "reroute", "dismiss"]);
  assert.strictEqual(new EmailViewModel(es[2], {}).dismissedReason, "accusé de réception");
  console.log("✓ ViewModel : confiance, proposition, actions — inerte et testé sans réseau");

  // — vue : les garanties historiques de renderMailList, une à une —
  const vms = es.map(e => new EmailViewModel(e, {}));
  assert(/file vide/.test(String(MailList([]))), "file vide non signalée");
  let out = String(MailList(vms));
  assert(/calyclay\/\?/.test(out), "client sans projet doit rester « /? »");
  assert(/80%/.test(out) && /contacts/.test(out), "confiance et source absentes");
  assert(/📎2/.test(out), "pièces jointes non signalées");
  assert(/↩ RM2661/.test(out), "réponse à un fil non signalée");
  assert(/→ RM2710/.test(out), "ticket créé non signalé");
  assert(/accusé de réception/.test(out), "motif d'écartement absent");
  assert(!/Créer le ticket/.test(out), "les actions ne doivent apparaître que sur l'email déplié");
  out = String(MailList([vmo]));
  assert(/id="ml-title" value="Caisse HS"/.test(out), "titre non pré-rempli");
  assert(/id="ml-project" value="calyclay\/dolibarr"/.test(out), "projet non pré-rempli");
  assert(/<option selected>high<\/option>/.test(out), "priorité non pré-sélectionnée");
  assert(/projet hors liste/.test(out), "avertissement de la proposition non affiché");
  assert(/tronqué à la relève/.test(out), "troncature du corps non signalée");
  ["Rédiger", "Créer le ticket", "Note sur…", "Reclasser", "Écarter"].forEach(a =>
    assert(out.includes(a), "action manquante : " + a));
  // l'invariant qui remplace « clé passée via jarg » : plus AUCUN handler inline
  assert(!/onclick=/.test(out), "un onclick inline a réapparu — les gestes passent par data-action");
  assert(/data-action="toggle"/.test(out) && /data-key="aaa1"/.test(out), "geste ou clé data-* absent");
  out = String(MailList([new EmailViewModel(EmailFactory.one({ key: "ddd4", subject: "<img src=x onerror=alert(1)>", from: "x@y.fr", date: "2026-08-14", routing: {} }), {})]));
  assert(!/<img/.test(out) && /&lt;img/.test(out), "sujet non échappé");
  const panel = String(MailPanel({ vms, pending: 3, done: true, fullBody: false, error: null }));
  assert(/— 3 à traiter/.test(panel) && /id="mail-done" style="width:auto" checked/.test(panel), "en-tête ou cases du panneau");
  assert(/<div class="empty">boum<\/div>/.test(String(MailPanel({ vms: [], pending: 0, done: false, fullBody: false, error: "boum" }))));
  console.log("✓ vue : file, routage, formulaire pré-rempli, échappement, zéro handler inline");

  // — service : la règle du message (dernière ligne non vide) et l'échec sans exception —
  const sent = [];
  const fakeRepo = {
    async send(kind, body) { sent.push([kind, body]); return kind === "dismiss"
      ? { ok: false, stderr: "x\nrefusé par le script\n" } : { ok: true, stdout: "…\n3 emails relevés\n" }; },
    async queue() { return { emails: es, pending: 2 }; },
    subscribe() { return () => {}; },
  };
  const svc = new MailService(fakeRepo);
  assert.deepStrictEqual(await svc.fetch(), { ok: true, message: "3 emails relevés" });
  assert.deepStrictEqual(await svc.dismiss("k", "why"), { ok: false, message: "Échec : refusé par le script" });
  await svc.noteOn("k", "RM 2889");
  assert.deepStrictEqual(sent.pop(), ["create", { key: "k", note_on: "2889" }], "note_on doit ne garder que les chiffres");
  console.log("✓ service : message = dernière ligne, échec rendu et non levé, note_on nettoyé");

  // — contrôleur : trois gestes, avec un service factice et un document minimal —
  const el = fakeElement(); const notes = []; const asked = [];
  const h = mountMailPanel(el, {
    service: svc, notify: (m, err) => notes.push([m, !!err]),
    ask: { confirm: (m) => { asked.push(m); return true; }, prompt: (m, d) => { asked.push(m); return d || "RM2889"; } },
    badge: (n) => notes.push(["badge", n]),
  });
  assert.strictEqual(el.listenerCount, 3, "un click + deux change, par délégation — quel que soit le nombre d'emails");
  await h.refresh();
  assert.strictEqual(h.state.pending, 2); assert(/Panne de caisse/.test(el.innerHTML));
  assert.deepStrictEqual(notes.pop(), ["badge", 2], "le badge de nav doit être informé");
  await el.click("toggle", "aaa1");
  assert.strictEqual(h.state.openKey, "aaa1", "toggle déplie");
  await el.click("toggle", "aaa1");
  assert.strictEqual(h.state.openKey, null, "toggle replie");
  await el.click("fetch");
  assert.deepStrictEqual(notes.find(n => n[0] === "3 emails relevés"), ["3 emails relevés", false]);
  await el.click("dismiss", "ccc3");
  assert(/^Motif/.test(asked.pop()) && sent.pop()[0] === "dismiss");
  await el.change("mail-done", true);
  assert.strictEqual(h.state.done, true, "la case « traités » recharge avec done=1");
  h.unmount();
  assert.strictEqual(el.listenerCount, 0, "unmount doit tout retirer");
  console.log("✓ contrôleur : gestes délégués, invites injectées, badge, démontage propre");

  console.log("\nTous les tests du domaine mail passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
