#!/usr/bin/env node
// Tests du panneau Fil (RM2792) : une FILE, pas un journal. Ce qui est traité sort de la vue, une
// notification privée se voit comme telle, le geste « tout » dit combien il emporte, et la pastille
// d'en-tête ne crie que quand quelque chose attend.
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
  const VM = await import(path.join(DIR, "src/modules/feed/FeedViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/feed/Feed.view.js"));
  const { mountFeed } = await import(path.join(DIR, "src/modules/feed/feed.controller.js"));

  const data = { viewer: "mathieu", users: ["claire", "mathieu"], counts: { open: 3, neuf: 2, worst: "critical" },
    feed: [
      { id: "aa", ts: "2026-09-14T01:00:00+02:00", last: "2026-09-14T01:20:00+02:00", origin: "scheduler",
        level: "warn", msg: "travail « backup » : échec", etat: "neuf", repeats: 4, job: "backup" },
      { id: "bb", ts: "2026-09-14T00:10:00+02:00", origin: "agent", level: "critical", msg: "clé d'API à renouveler",
        etat: "neuf", repeats: 1, user: "mathieu", private: true, rm: "2429" },
      { id: "cc", ts: "2026-09-13T22:00:00+02:00", origin: "session", level: "info", msg: "revue livrée",
        etat: "traite", repeats: 1 },
    ] };

  // ── le ViewModel décide ─────────────────────────────────────────────────────
  const vm = new VM.FeedViewModel({ data, etat: "ouvert" });
  const rows = vm.rows();
  assert.strictEqual(rows.length, 3);
  assert.strictEqual(rows[0].repeats, 4, "la répétition est un compteur, pas trois lignes de plus");
  assert(rows[1].prive && rows[1].user === "mathieu", "une entrée privée se sait privée");
  assert(rows[2].traite, "et le traité reste identifiable");
  assert.deepStrictEqual(vm.vues.map(v => [v.key, v.on]), [["ouvert", true], ["tout", false]],
    "le fil s'ouvre sur ce qui ATTEND — un fil qui s'ouvre sur le traité n'est plus une file");
  assert.deepStrictEqual(vm.users.map(u => u.key), ["", "claire", "mathieu"], "« tout le monde » d'abord");
  assert.strictEqual(vm.users[0].on, true, "sans filtre, c'est « tout le monde » qui est actif");
  assert.strictEqual(new VM.FeedViewModel({ data: { feed: [] } }).empty, true);

  // ── la vue montre ce qu'il faut, et rien en on* ─────────────────────────────
  const card = String(V.FeedCard(vm));
  assert(/🔔 Fil/.test(card) && /3 en attente/.test(card) && /2 non lue\(s\)/.test(card) && /pire niveau : critical/.test(card));
  assert(/×4/.test(card), "la répétition est visible");
  assert(/🔒mathieu/.test(card), "le privé est marqué dans la page, pas seulement dans les données");
  assert(/data-action="ticket" data-rm="2429"/.test(card), "une notification qui cite un ticket y mène");
  assert(/data-action="done-all"/.test(card), "le geste « tout » existe dans la vue « ce qui attend »");
  assert(/lu au nom de <b>mathieu<\/b>/.test(card), "le lecteur est nommé : c'est ce qui explique ce qu'on ne voit pas");
  assert(!/\son(click|change|input)=/.test(card), "aucun handler inline");
  const anon = String(V.FeedCard(new VM.FeedViewModel({ data: Object.assign({}, data, { viewer: "" }) })));
  assert(/les entrées privées n'apparaissent pas/.test(anon), "sans lecteur, la page DIT pourquoi le fil est incomplet");
  assert(/fil illisible : boum/.test(String(V.FeedCard(new VM.FeedViewModel({ error: "boum" })))));

  // ── le contrôleur marque, et ne décide de rien ──────────────────────────────
  const calls = []; const toasts = []; let asked = "";
  const svc = { data, error: null,
    async load(o) { calls.push(["load", o]); return data; },
    async mark(b) { calls.push(["mark", b]); return { marked: (b.ids || []).length || 3 }; } };
  const el = fakeEl("feedcard");
  let counts = null;
  const ctr = mountFeed(el, { service: svc, notify: (m) => toasts.push(m), confirm: (m) => { asked = m; return true; },
                                onCounts: (c) => { counts = c; }, showTicket: (rm) => calls.push(["ticket", rm]) });
  await ctr.open();
  assert(/🔔 Fil/.test(el.innerHTML) && /travail « backup »/.test(el.innerHTML));

  calls.length = 0; await el.click("lu", { id: "aa" });
  assert.deepStrictEqual(calls[0], ["mark", { ids: ["aa"], etat: "lu" }], "« lue » laisse l'entrée dans la file");
  calls.length = 0; await el.click("done", { id: "aa" });
  assert.deepStrictEqual(calls[0], ["mark", { ids: ["aa"], etat: "traite" }], "« traitée » la fait sortir de la vue");

  calls.length = 0; await el.click("done-all");
  assert(/3 notification\(s\)/.test(asked), "« tout » dit combien il emporte avant de le faire");
  assert.deepStrictEqual(calls[0], ["mark", { all: true, etat: "traite" }]);
  assert(toasts.some(t => /3 notification\(s\) traitée\(s\)/.test(t)));

  calls.length = 0; await el.click("vue", { vue: "tout" });
  assert.strictEqual(ctr.state.etat, "tout"); assert.deepStrictEqual(calls[0][1], { etat: "tout", user: "" });
  await el.click("user", { user: "claire" });
  assert.strictEqual(ctr.state.user, "claire", "le filtre par personne est un filtre d'affichage");
  calls.length = 0; await el.click("ticket", { rm: "2429" });
  assert.deepStrictEqual(calls[0], ["ticket", "2429"], "le fil mène au ticket, il ne l'ouvre pas lui-même");

  await ctr.poll(); assert.deepStrictEqual(counts, data.counts, "la pastille reçoit les compteurs");

  // le fil ne casse pas ce qu'il observe
  const svc2 = { data: null, error: "réseau", async load() { return null; }, async mark() { throw new Error("refusé"); } };
  const el2 = fakeEl("c2"); const t2 = [];
  const ctr2 = mountFeed(el2, { service: svc2, notify: (m) => t2.push(m) });
  await ctr2.open(); assert(/fil illisible/.test(el2.innerHTML));
  await el2.click("done", { id: "x" }); assert(t2.some(m => /refusé/.test(m)), "un marquage refusé se dit, il ne casse pas la page");

  // ── câblage : le panneau, le bouton, et le tick qui porte le compteur ───────
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/id="cp-feed"/.test(html) && /id="feedcard"/.test(html), "le panneau a son hôte");
  const btn = /<button[^>]*id="feedbtn"[^>]*>/.exec(html);
  assert(btn && /data-cmd="panel" data-arg="feed"/.test(btn[0]) && !/\son\w+=/.test(btn[0]),
    "le bouton d'en-tête ouvre le panneau, sans handler inline");
  assert(/feed:\s+\{ label: "fil"/.test(boot), "le panneau est déclaré dans le registre");
  assert(/onSessions: \(list\) => \{ sessionsCtl\.render\(list\); pollFeed\(\); \}, onWorklog:/.test(boot) && /t - feedAt < 60000/.test(boot) && /feedBusy/.test(boot),
    "RM2792 : le compte suit le tick existant — bridé, et jamais deux lectures en vol");
  const css = fs.readFileSync(path.join(DIR, "cockpit.css"), "utf8");
  assert(/#feedbtn\.has-critical/.test(css), "la pastille sait crier — et seulement quand c'est critique");

  console.log("✓ panneau Fil (RM2792) : file, confidentialité visible, gestes, câblage");
})().catch(e => { console.error(e); process.exit(1); });
