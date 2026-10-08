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
  // RM3300 : deux gestes de lot, et chacun DIT ce qu'il fait — « tout » seul ne disait rien.
  assert(/data-action="done-all"[^>]*>✓ tout traiter</.test(card), "« tout traiter » nomme son effet");
  assert(/data-action="lu-all"[^>]*>○ tout lire</.test(card), "« tout lire » existe à côté");
  assert(/Marquer lues les 2 notification\(s\) non lue\(s\)/.test(card), "…et annonce combien, avant le clic");
  assert(/Marquer traitées les 3 notification\(s\)/.test(card));
  { const luesToutes = String(V.FeedCard(new VM.FeedViewModel({ data: Object.assign({}, data, { counts: { open: 3, neuf: 0, worst: "critical" } }) })));
    assert(!/data-action="lu-all"/.test(luesToutes), "rien à lire : le bouton disparaît, il ne reste pas inerte");
    assert(/data-action="done-all"/.test(luesToutes), "…l'autre reste"); }
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

  calls.length = 0; toasts.length = 0; await el.click("lu-all");
  assert(/2 notification\(s\)/.test(asked), "« tout lire » dit combien il emporte");
  assert(/restent dans la file/.test(asked), "…et ce qu'il ne fait PAS : elles ne sortent pas de la vue");
  assert.deepStrictEqual(calls[0], ["mark", { all: true, etat: "lu" }], "lot « lu », sans filtre de personne quand il n'y en a pas");
  assert(toasts.some(t => /notification\(s\) marquée\(s\) lue\(s\)/.test(t)));

  // un refus de confirmation ne doit RIEN envoyer : le geste ne se défait pas
  { const calls2 = []; const el2 = fakeEl();
    const svc2 = { load: async () => data, mark: async (b) => { calls2.push(b); return { marked: 0 }; }, data: null };
    const c2 = mountFeed(el2, { service: svc2, notify: () => {}, confirm: () => false });
    await c2.open();
    await el2.click("lu-all"); await el2.click("done-all");
    assert.strictEqual(calls2.length, 0, "confirmation refusée : aucun appel serveur, ni pour lire ni pour traiter"); }

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

  // ── RM3206 : le CONTEXTE — de quoi ça parle, et où ──────────────────────────────────────
  const FVM = await import(path.join(DIR, "src/modules/feed/FeedViewModel.js"));
  const ligne = {
    id: "x", level: "warn", etat: "neuf", origin: "system", msg: "la précharge a entamé sa marge",
    job: "norms-budget", tokens: 28048, budget: 29000, pct: 97,
    rm: "3153", sid: "fbfafc14-8276-49cc", client: "iprospective", projet: "pm-ai-agents",
    repeats: 12, ts: "2026-09-13T10:00:00+02:00", last: "2026-09-16T10:00:00+02:00" };
  const r = new FVM.FeedViewModel({ data: { feed: [ligne] } }).rows()[0];
  assert.strictEqual(r.job, "norms-budget", "l'origine PRÉCISE survit au rendu — « system » ne situe rien");
  assert.strictEqual(r.client, "iprospective"); assert.strictEqual(r.projet, "pm-ai-agents");
  assert.strictEqual(r.sid, "fbfafc14-8276-49cc"); assert.strictEqual(r.rm, "3153");
  // toLocaleString("fr-FR") sépare les milliers par une FINE INSÉCABLE (U+202F) : on compare la
  // forme, pas le caractère d'espacement, sinon le test casse au gré de la locale du système.
  const esp = (s) => String(s).replace(/[\s\u202f\u00a0]+/g, " ");
  assert.strictEqual(esp(r.mesure), "28 048 / 29 000 (97 %)",
    "la mesure se lit d'un coup d'œil ; le message seul ne situe pas");
  assert.strictEqual(r.fenetre, "3 j",
    "×12 en dix minutes et ×12 sur trois jours appellent des réactions opposées");
  // une notification sans mesure ni répétition ne fabrique pas de bruit
  const nu = new FVM.FeedViewModel({ data: { feed: [{ id: "y", level: "info", msg: "rien de plus" }] } }).rows()[0];
  assert.strictEqual(nu.mesure, ""); assert.strictEqual(nu.fenetre, "");
  assert.strictEqual(nu.job, ""); assert.strictEqual(nu.client, "");
  assert.strictEqual(FVM.fenetre("2026-09-16T10:00:00+02:00", "2026-09-16T10:30:00+02:00"), "30 min");
  assert.strictEqual(FVM.fenetre("2026-09-16T10:00:00+02:00", "2026-09-16T15:00:00+02:00"), "5 h");
  assert.strictEqual(FVM.fenetre("bidon", "aussi"), "", "des dates illisibles ne rendent pas « NaN »");
  assert.strictEqual(esp(FVM.mesure({ pct: 97 })), "97 %", "un pourcentage seul reste lisible");
  const vue = fs.readFileSync(path.join(DIR, "src/modules/feed/Feed.view.js"), "utf8");
  assert(/data-action="ticket"/.test(vue), "le ticket est un LIEN, pas un texte");
  assert(/feed-ou/.test(vue) && /feed-sid/.test(vue) && /feed-job/.test(vue) && /feed-mes/.test(vue),
    "projet/client, session, job et mesure sont rendus");
  const scss = fs.readFileSync(path.join(DIR, "src/modules/feed/feed.scss"), "utf8");
  assert(/\.feed-ou/.test(scss) && /\.feed-mes/.test(scss), "le contexte a ses styles — discret, il situe sans concurrencer le message");

  // ── RM3177 : la TENDANCE et les invariants rouges ────────────────────────────────────
  const avecPente = new FVM.FeedViewModel({ data: { feed: [{ id: "t", level: "warn", msg: "marge",
    tokens: 29518, budget: 30000, pct: 98, tendance: 5.3, tendance_jours: 21 }] } }).rows()[0];
  assert.strictEqual(esp(avecPente.mesure), "29 518 / 30 000 (98 %), +5,3 pts en 21 j",
    "« 98 % » ne distingue pas un plateau d'une dérive ; la pente dit ce qu'il faut faire");
  assert.strictEqual(esp(FVM.tendance({ tendance: -3, tendance_jours: 10 })), ", -3 pts en 10 j", "une baisse se dit négative");
  assert.strictEqual(FVM.tendance({ tendance: null }), "", "pas de pente connue : on n'invente rien");
  assert.strictEqual(FVM.tendance({ tendance: 2, tendance_jours: 0 }), "", "une pente sans durée ne veut rien dire");
  const doc = new FVM.FeedViewModel({ data: { feed: [{ id: "d", level: "warn", msg: "des invariants NORMS sont rouges",
    job: "norms-doctor", invariants: ["non-perte", "index PÉRIMÉ"] }] } }).rows()[0];
  assert.deepStrictEqual(doc.invariants, ["non-perte", "index PÉRIMÉ"], "le message est stable, la LISTE dit lesquels");
  assert.deepStrictEqual(nu.invariants || [], [], "une notification sans invariants n'en fabrique pas");
  assert(/feed-inv/.test(fs.readFileSync(path.join(DIR, "src/modules/feed/Feed.view.js"), "utf8")), "les invariants sont rendus");

  console.log("✓ panneau Fil (RM2792/RM3206/RM3177) : file, confidentialité, gestes, câblage, contexte, tendance, invariants");
})().catch(e => { console.error(e); process.exit(1); });
