#!/usr/bin/env node
// Tests de la surface « revue » migrée (RM2889, revue 2/3) — porte RM2726 (sessions du ticket), RM2786 (verdicts),
// RM2818 (doublon), RM2832 (étiquettes), RM2833 (rôle), RM2873 (consigne), RM2888 (menu de statut, invites, gardes).
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 10));
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function fakeElement() { const L = []; let inner = ""; const sub = {}; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, sub, remove() { sub.removed = true; },
  querySelector(sel) { return sub[sel] || null; },
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async click(action, data) { const n = { dataset: { action, ...(data || {}) }, disabled: false }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => (s === "[data-action]" ? n : s === "button[data-st]" && data && data.st ? { dataset: { st: data.st, reason: data.reason, note: data.note } } : null) }, stopPropagation() {} }); return n; },
  async fire(type, sel, n) { for (const [t, f] of [...L]) if (t === type) await f({ target: { closest: s => s === sel ? n : null } }); } }; }
(async () => {
  const ST = await import(path.join(DIR, "src/modules/ticket/ticketStatus.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const P = await import(path.join(DIR, "src/modules/ticket/prompts.js"));
  const { effDisposition } = await import(path.join(DIR, "src/modules/ticket/ticketFormat.js"));
  const VM = await import(path.join(DIR, "src/modules/review/ReviewViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/review/Review.view.js"));
  const { ReviewService } = await import(path.join(DIR, "src/modules/review/review.service.js"));
  const { mountReview } = await import(path.join(DIR, "src/modules/review/review.controller.js"));
  // — RM2786 : verdicts par statut —
  const CFG = { closable_statuses: ["a_mep", "a_tester_demandeur", "a_tester_dev", "en_mep"], statuses: ["nouveau", "a_etudier_chiffrer", "etude_chiffrage_en_cours", "etude_chiffrage_a_valider", "a_faire", "en_cours", "a_corriger", "a_tester_dev", "a_tester_demandeur", "a_mep", "en_mep", "en_pause", "ferme"] };
  assert.deepEqual(ST.ticketVerdicts("en_cours", CFG), []); assert.strictEqual(ST.ticketVerdicts("a_tester_demandeur", CFG).length, 3); assert.deepEqual(ST.ticketVerdicts("a_mep", CFG).map(v => v.kind), ["valider", "renvoyer"]);
  assert.strictEqual(ST.ticketVerdicts("statut_inconnu", CFG).length, 3); assert.strictEqual(ST.ticketVerdicts("", CFG).length, 3);
  assert.strictEqual(ST.gateKind("… checklist non cochée …"), "checklist"); assert.strictEqual(ST.gateKind("branche non mergée (RM2319)"), "merge"); assert.strictEqual(ST.gateKind("autre"), null);
  // — RM2888 : invites —
  const spF = ST.statusPromptSpec("ferme", true, ["abandonne", "resolu", "doublon"], false); assert.strictEqual(spF.needs_reason, true); assert.strictEqual(spF.default_reason, "resolu"); assert(/facultatif/.test(spF.note_label));
  const spR = ST.statusPromptSpec("a_faire", false, [], true); assert.strictEqual(spR.needs_note, true); assert(/requise/.test(spR.note_label)); assert.strictEqual(ST.statusPromptSpec("en_cours", false, [], false).needs_reason, false); assert.strictEqual(ST.statusPromptSpec("ferme", true, [], false).default_reason, "");
  console.log("✓ statuts (RM2786/RM2888) : verdicts par statut, gardes reconnues, invites décidées par le serveur");
  // — RM2888 : menu —
  const menu = (d) => String(V.StatusMenu(new VM.StatusMenuViewModel(d)));
  const stData = { status: "en_cours", redmine_checked: true, transitions: [{ status: "a_tester_dev", condition: "dev terminé", redmine_ok: true }, { status: "a_mep", condition: "validé", redmine_ok: false }, { status: "ferme", condition: "close_reason requis", redmine_ok: true, needs_close_reason: true }] };
  const st = menu(stData);
  assert(/data-st="a_tester_dev"/.test(st) && /data-st="a_mep"[^>]*disabled/.test(st) && /Redmine refusera/.test(st) && /data-st="ferme"[^>]*data-reason="1"/.test(st) && !/⚠ transitions NORMS seules/.test(st));
  const deg = menu({ status: "a_faire", redmine_checked: false, transitions: [{ status: "en_cours", condition: "prise en charge", redmine_ok: null }] }); assert(/data-st="en_cours"/.test(deg) && !/disabled/.test(/data-st="en_cours"[^>]*>/.exec(deg)[0]) && /⚠ transitions NORMS seules/.test(deg));
  assert(/aucune transition/.test(menu({ status: "ferme", transitions: [] })) && /aucune transition/.test(menu(null)));
  const viewSrc = require("fs").readFileSync(path.join(DIR, "src/modules/review/Review.view.js"), "utf8") + require("fs").readFileSync(path.join(DIR, "src/modules/review/review.controller.js"), "utf8");
  for (const s of CFG.statuses) assert(!viewSrc.includes('"' + s + '"'), "aucun statut en dur dans la vue ni le contrôleur : " + s);
  // RM3238 : MEP prod verrouillée par des questions non tranchées, questions nommées dans l'infobulle
  const gq = menu({ status: "a_mep", redmine_checked: true, transitions: [{ status: "en_mep", condition: "déployé", redmine_ok: true, blocked_by_questions: ["Q001", "Q003"] }, { status: "en_pause", condition: "blocage", redmine_ok: true, blocked_by_questions: [] }] });
  assert(/data-st="en_mep"[^>]*disabled/.test(gq) && /Q001, Q003/.test(gq) && /non tranchée/.test(gq), "une MEP bloquée par des questions est verrouillée et dit lesquelles");
  assert(!/disabled/.test(/data-st="en_pause"[^>]*>/.exec(gq)[0]), "une transition sans question en cause reste ouverte");
  console.log("✓ menu de statut (RM2888) : le serveur décide, l'UI rend — refus, mode dégradé, zéro règle recopiée");
  // — RM2726 / RM2873 / RM2833 : consignes —
  assert.strictEqual(P.taskPromptText("traiter", "2726", "iprospective", "pm-ai-agents"), "traite la tâche RM2726 du client iprospective projet pm-ai-agents");
  assert.strictEqual(P.taskPromptText("traiter", "2726", "", ""), "traite la tâche RM2726"); assert.strictEqual(P.taskPromptText("traiter", "abc"), ""); assert.strictEqual(P.taskPromptText("zzz", "2726"), "");
  assert(/relis le \.log\.md/.test(P.taskPromptText("continuer", "2726")) && /SANS rien modifier/.test(P.taskPromptText("etat", "2726")));
  const p33 = P.taskPromptText("traiter", "42", "acme", "shop", { role: "db", file: "agents/worker-db.md" }); assert(/RM42/.test(p33) && /worker-db\.md/.test(p33)); assert(!/worker-/.test(P.taskPromptText("reviewer", "42", "acme", "shop", { role: "db" })));
  assert.strictEqual(P.roleHintLine({ role: "db", file: "agents/worker-db.md" }), " (rôle suggéré : db — agents/worker-db.md)"); assert.strictEqual(P.roleHintLine(null), ""); assert.strictEqual(P.roleHintLine({}), "");
  const tpls = P.promptTemplates(); assert(tpls.length >= 5 && tpls.every(t => t.value && t.label) && tpls[tpls.length - 1].value === "libre" && tpls.every(t => t.value === "libre" || P.taskPromptText(t.value, "42")));
  assert.strictEqual(P.promptFillOnChange("libre", "ma consigne à moi", "traite la tâche RM42"), "ma consigne à moi"); assert.strictEqual(P.promptFillOnChange("traiter", "vieux texte", "traite la tâche RM42"), "traite la tâche RM42"); assert.strictEqual(P.promptFillOnChange("traiter", "déjà tapé", ""), "déjà tapé");
  assert.strictEqual(P.ticketPromptFor(null, "42", "traite la tâche RM42").text, "traite la tâche RM42"); const s2 = P.ticketPromptFor({ rm: "42", tpl: "libre", text: "fais autre chose" }, "42", "x"); assert.strictEqual(s2.text, "fais autre chose"); assert.strictEqual(s2.tpl, "libre"); assert.strictEqual(P.ticketPromptFor({ rm: "42", tpl: "libre", text: "fais autre chose" }, "43", "traite la tâche RM43").text, "traite la tâche RM43");
  const busy = { alive: [{ sid: "2700", state: "working", title: "en cours" }, { sid: "parke", state: "idle", disposition: "parke", title: "parké" }], stopped: [{ sid: "vieille", state: "ghost", title: "hier" }] };
  const txt = P.duplicateSessionText("2816", busy, effDisposition); assert(txt.includes("2700") && txt.includes("parke") && txt.includes("RM2816") && /éteinte/i.test(txt) && /parké/.test(txt));
  console.log("✓ consignes (RM2726/2833/2873) et alerte de doublon (RM2818) : formulation unique, saisie préservée, texte nommé");
  // — RM2726 : sessions du ticket (vue) ; RM2832 : étiquettes —
  const ts = (d, pr) => String(V.TicketSessions(new VM.TicketSessionsViewModel(d, { prompt: pr })));
  const tsNone = ts({ rm_id: "2726", handled: [], candidates: [], live: false, own_alive: false });
  assert(/aucune session ne traite ce ticket/.test(tsNone) && /data-action="spawn" data-rm="2726"/.test(tsNone) && !/disabled/.test(tsNone) && /aucune autre session vivante/.test(tsNone));
  const tsData = { rm_id: "2726", client: "iprospective", project: "pm-ai-agents", live: true, own_alive: true, handled: [{ sid: "2726", alive: true, reasons: ["ancrage"], title: "[WIP] fiche", same_project: true }, { sid: "vieille", alive: false, reasons: ["registre"], title: "hier", same_project: true }],
    candidates: [{ sid: "cockpit", alive: true, title: "cockpit", same_project: true }, { sid: "presta", alive: true, title: "presta", same_project: false, client: "acme", project: "boutique" }] };
  const tsOut = ts(tsData, { tpl: "chiffrer", text: "étudie et chiffre la tâche RM2726" });
  assert(/karl-RM2726/.test(tsOut) && /karl-vieille/.test(tsOut) && /ancrage/.test(tsOut) && /registre/.test(tsOut) && /data-action="attach" data-sid="2726"/.test(tsOut) && !/data-sid="vieille"/.test(tsOut) && /éteinte/.test(tsOut) && /disabled/.test(tsOut));
  assert(/<optgroup label="iprospective\/pm-ai-agents">[\s\S]*cockpit/.test(tsOut) && tsOut.indexOf('label="iprospective/pm-ai-agents"') < tsOut.indexOf('label="autres projets"') && /acme\/boutique/.test(tsOut) && /data-action="send" data-rm="2726"/.test(tsOut));
  assert(/id="ts-tpl"/.test(tsOut) && /<option value="chiffrer" selected>/.test(tsOut) && /étudie et chiffre la tâche RM2726<\/textarea>/.test(tsOut) && /data-prompt="text"/.test(tsOut) && !/onclick=|oninput=|onchange=/.test(tsOut));
  assert(/recherche des sessions/.test(ts(null))); assert(!/<img/.test(ts({ rm_id: "1", handled: [{ sid: "x", alive: true, reasons: ["worklog"], title: '<img src=x onerror=alert(1)>' }], candidates: [], own_alive: false })));
  const tp = String(V.TagPills(["front", "refacto"])); assert(/front/.test(tp) && /🏷/.test(tp) && /data-action="tag" data-tag="refacto"/.test(tp)); assert.strictEqual(String(V.TagPills([])), ""); assert(!/onclick="alert/.test(String(V.TagPills(['a" onclick="alert(1)']))) && /&quot;/.test(String(V.TagPills(['a" onclick="alert(1)']))) && /&lt;b&gt;/.test(String(V.TagPills(["<b>"]))));
  console.log("✓ sessions du ticket (RM2726) et étiquettes (RM2832) : source affichée, envoi ciblé, consigne, échappement");
  // — la fiche entière —
  const R = { found: true, title: "Titre", client: "acme", project: "shop", status: "a_tester_demandeur", priority: "high", tags: ["front"], updated: "2026-09-05T10:00", redmine_url: "https://r", git: { mr_url: "https://mr" }, test_protocol: { text: "# proto", source: "note" }, description: "desc", log_tail: "log", environments: [{ name: "prod", url: "https://p" }], test_url: "https://t" };
  const fiche = (over) => String(V.ReviewPane(new VM.ReviewViewModel(Object.assign({ r: R, q: { branch: "b", test_host: "h", env_live: true }, tqLoaded: true, tqSize: 1, mc: { verdict: { level: "ok", headline: "ok" } }, ts: tsData, cfg: Object.assign({ actions: [{ label: "→ en cours", text: "passe RM{id}", ticket_only: true }] }, CFG), pmTarget: { sid: "42", why: "session du ticket" } }, over || {}), { rm: "2726", prompt: { tpl: "traiter", text: "t" }, now: Date.parse("2026-09-05T11:00") }), { md: (s) => "<md>" + s + "</md>", titleLink: (rm, t) => "<i>" + esc(t) + "</i>", mcBanner: (mc) => '<div class="mcbanner">' + mc.verdict.headline + "</div>" }));
  const f = fiche();
  assert(/🧪 RM2726 — <i>Titre<\/i>/.test(f) && /acme\/shop/.test(f) && /version il y a 1 h/.test(f) && /data-action="reload"/.test(f) && /Redmine ↗/.test(f) && /MR ↗/.test(f) && /branche <span class="pill"/.test(f));
  // RM3256 : les champs du ticket viennent du registre d'entités (une seule description, deux vues) ;
  // la fiche ne garde que ce qui lui est propre : env de test, cohérence git, verdicts.
  assert(/data-sec="protocol"[\s\S]*\(note de livraison\)[\s\S]*<h1>proto<\/h1>/.test(f), "protocole : provenance + markdown, depuis le registre");
  assert(/data-sec="description"[\s\S]*<p>desc<\/p>/.test(f) && /data-sec="log"[\s\S]*log/.test(f), "description (en markdown) et dernière activité aussi");
  assert(/data-sec="environments"[\s\S]*https:\/\/p/.test(f), "environnements du projet : une seule définition");
  assert(/🔗 <a href="http:\/\/h\/"/.test(f) && /data-action="env-teardown"/.test(f) && /class="mcbanner">ok/.test(f), "… et l'env de test du ticket reste propre à la fiche");
  assert(!/<h4>📋 Protocole de test<\/h4>/.test(f) && !/📝 Description du ticket/.test(f), "la fiche ne redécrit plus ces champs");
  assert(/data-action="verdict" data-kind="valider"/.test(f) && /data-action="pm" data-i="0" data-rm="2726"/.test(f) && /title="passe RM2726"/.test(f) && /session du ticket/.test(f) && !/onclick=/.test(f));
  assert(/data-action="env-deploy"/.test(fiche({ q: { test_host: "h", env_reason: "down" } })) && /down/.test(fiche({ q: { test_host: "h", env_reason: "down" } })), "env présent mais indisponible → re-déployer");
  assert(/data-action="env-shared"/.test(fiche({ q: { deployable: true } })) && /hors layout/.test(fiche({ q: {} })) && /n’est plus dans la file de test/.test(fiche({ q: undefined })) && /data-action="close"/.test(fiche({ q: undefined })));
  assert(/hors file de test/.test(fiche({ q: undefined, tqLoaded: false, tqSize: 3 })) && /chargement de l’état/.test(fiche({ q: undefined, tqLoaded: false, tqSize: 0 })));
  // RM3137 : une description est repliée à la source vers 80 colonnes (convention d'écriture des
  // fiches). Rendue dans un <pre>, ces retours à la ligne étaient préservés : le texte se coupait à
  // l'écran quelle que soit la largeur disponible. Le niveau « full » du registre d'entités était le
  // dernier endroit qui la rendait ainsi — la fiche de revue, elle, passait déjà par le markdown.
  const repliee = "Une phrase assez longue qui a été coupée par l'auteur\nvers quatre-vingts colonnes, et qui doit se relire\nd'un seul tenant.\n\nUn second paragraphe.\n\n```\nbloc  de   code\nligne 2\n```\n\n- une puce\n- une autre";
  const secDesc = (d) => String(new VM.ReviewViewModel({ r: Object.assign({}, R, { description: d }) }, { rm: "2726" })
    .sections().find(x => x.id === "description").body());
  const md3137 = secDesc(repliee);
  assert(!/<pre>Une phrase/.test(md3137), "la description n'est plus un listing brut");
  assert(/<p>Une phrase assez longue qui a été coupée par l'auteur vers quatre-vingts colonnes, et qui doit se relire d'un seul tenant.<\/p>/.test(md3137),
         "les sauts de ligne simples sont JOINTS — c'est la fenêtre qui décide où la ligne s'arrête");
  assert(/<p>Un second paragraphe.<\/p>/.test(md3137), "une ligne vide sépare toujours deux paragraphes");
  assert(/bloc  de   code/.test(md3137) && /<pre>/.test(md3137), "un bloc de code garde sa forme, espaces compris");
  assert(/une puce/.test(md3137) && /<li>|<ul>/.test(md3137), "une liste reste une liste");
  assert(/class="mdview"/.test(md3137), "le rendu porte la classe qui l'habille (retour à la ligne normal)");
  assert(!/<script>/.test(secDesc("<script>alert(1)</script>")),
         "et le markdown échappe avant de transformer — une description est du texte d'utilisateur");

  const fEnCours = fiche({ r: Object.assign({}, R, { status: "en_cours" }) }); assert(!/data-action="verdict"/.test(fEnCours) && /Aucun verdict à rendre/.test(fEnCours) && /data-action="pm"/.test(fEnCours), "ticket en cours : actions PM oui, verdicts non");
  assert(/vérification de la mergeabilité en cours/.test(fiche({ mc: null })));
  console.log("✓ fiche de revue : en-tête daté, protocole, env de test (6 états), cohérence git, actions filtrées par statut");
  // — le service : gardes explicites, jamais d'office —
  const runs = []; let outs = {};
  const run = async (name, args) => { runs.push([name, JSON.parse(JSON.stringify(args))]); const key = args.allow_unchecked ? "forced" : "first"; return outs[key] || { ok: true, rc: 0, stdout: "ok" }; };
  const repo = { async deliver(rm) { runs.push(["deliver", rm]); return { ok: true }; }, invalidateTransitions(rm) { runs.push(["inval", rm]); }, async transitions(rm) { return stData; }, async ensureTicketSessions(rm, f) { return { handled: [{ sid: "9", alive: true, state: "working" }] }; }, async spawn(b) { runs.push(["spawn", b]); return { ok: true }; }, async send(sid, msg) { runs.push(["send", sid, msg]); return {}; } };
  const svc = new ReviewService({ repo, run, eff: effDisposition });
  outs = { first: { ok: false, rc: 1, stdout: "checklist non cochée" }, forced: { ok: true, rc: 0 } }; const asked = [];
  let r = await svc.verdict("42", "valider", "note", (m) => { asked.push(m); return true; }); assert(r.ok && runs.filter(x => x[0] === "task-status").length === 2 && runs[1][1].allow_unchecked === true && /checklist/.test(asked[0]), "garde checklist : montrée, puis forcée sur accord");
  runs.length = 0; asked.length = 0; r = await svc.verdict("42", "valider", "note", () => false); assert(!r.ok && runs.length === 1, "refus → pas de second appel");
  runs.length = 0; outs = { first: { ok: false, rc: 1, stderr: "branche non mergée (RM2319)" } }; r = await svc.applyStatus("42", "ferme", { note: "n", reason: "resolu" }, () => true, () => {}); assert(runs.some(x => x[0] === "deliver") && runs.filter(x => x[0] === "task-status").length === 2 && runs.some(x => x[0] === "inval"), "merge gate : livrer (MR + merge) puis rejouer, et invalider les transitions");
  assert.deepStrictEqual(runs[0][1], { rm_id: "42", status: "ferme", note: "n", close_reason: "resolu" });
  const b2 = await svc.busyFor("42"); assert.deepStrictEqual(b2.alive.map(s => s.sid), ["9"]);
  console.log("✓ service : gardes NORMS franchies explicitement (checklist, merge gate), jamais avalées ni forcées d'office");
  // — le contrôleur —
  const el = fakeElement(); const ev = []; const resolve = mkStore("r", { "42": Object.assign({}, R, { status: "a_tester_demandeur" }) });
  const T = { repo: { s: { mc: mkStore("mc"), ts: mkStore("ts") } }, ensureResolved: async (rm) => { ev.push(["resolve", rm]); return resolve.get(rm); }, revalidate: async () => {}, ensureMergecheck: async () => {}, ensureTicketSessions: async () => {}, mcBanner: () => "", reload: async (rm) => ev.push(["reload", rm]) };
  const center = { yield: (k) => ev.push(["yield", k]), note: (...a) => ev.push(["note", ...a]), title: () => {}, fallback: () => ev.push("fallback") };
  const ctr = mountReview(el, { ticket: T, service: svc, center, notify: (m, e) => ev.push(["toast", m, !!e]), confirm: () => true, prompt: () => "ma note", resolve: () => resolve, cfg: () => CFG, show: (on) => ev.push(["show", on]), setMeta: (rm) => ev.push(["meta", rm]), renderMeta: () => ev.push("renderMeta"), noteOpened: (rm) => ev.push(["opened", rm]), showRight: (t) => ev.push(["right", t]), refreshSessions: () => ev.push("sessions"), attach: (s) => ev.push(["attach", s]), tq: { entry: () => ({ branch: "b" }), loaded: () => true, size: () => 1, load: () => ev.push("tqload") }, launcher: () => ({ engine: "claude", model: "" }), popover: () => { const m = fakeElement(); el.sub.menu = m; return m; }, place: () => {}, onOutsideClick: () => {} });
  ctr.open("42"); assert.deepStrictEqual(ev.slice(0, 5), [["opened", "42"], ["yield", "review"], ["meta", "42"], ["show", true], ["note", "review", "42", "RM42"]]); assert.strictEqual(ctr.current(), "42"); assert.deepStrictEqual(ctr.tabs(), ["42"]); assert(/🧪 RM42/.test(el.innerHTML));
  await new Promise(r2 => setTimeout(r2, 0)); ctr.open("43"); assert.deepStrictEqual(ctr.tabs(), ["42", "43"]); ctr.close("43"); assert.strictEqual(ctr.current(), null); assert(ev.includes("fallback")); assert.deepStrictEqual(ctr.tabs(), ["42"]);
  ctr.open("42"); ctr.yieldTo(); assert.strictEqual(ctr.current(), null); assert.deepStrictEqual(ctr.tabs(), ["42"], "céder la place ne ferme pas l'onglet");
  ctr.open("42"); await el.fire("change", "[data-prompt]", { dataset: { prompt: "tpl" }, value: "chiffrer" }); assert(/^étudie et chiffre la tâche RM42/.test(ctr.state.prompt.text), "changer de modèle recalcule la consigne");
  await el.fire("input", "[data-prompt]", { dataset: { prompt: "text" }, value: "libre à moi" }); assert.strictEqual(ctr.promptText("42"), "libre à moi", "la saisie vit hors du DOM et fait foi");
  runs.length = 0; outs = {}; await el.click("verdict", { kind: "mep", rm: "42" }); await settle(); assert(runs.some(x => x[0] === "task-status" && x[1].status === "a_mep" && x[1].note === "ma note") && ev.some(x => x[0] === "toast" && /RM42 → a_mep/.test(x[1])) && ev.includes("tqload"), "verdict : task-status avec la note, puis la file rechargée");
  await el.click("spawn", { rm: "42" }); await settle(); assert(ev.some(x => x[0] === "attach" && x[1] === "9"), "une session travaille déjà le ticket → on la rejoint (RM2818)");
  await ctr.openStatusMenu("RM42", { getBoundingClientRect: () => ({ left: 0, bottom: 0 }) }); await settle(); assert(/data-st="a_tester_dev"/.test(el.sub.menu.innerHTML), "le menu est chargé APRÈS ouverture, depuis les transitions du serveur");
  runs.length = 0; await el.sub.menu.click("x", { st: "a_tester_dev" }); await settle(); assert(runs.some(x => x[0] === "task-status" && x[1].status === "a_tester_dev"), "choisir une transition la soumet"); assert(el.sub.menu.sub.removed, "…et referme le menu");
  // RM3258 — une entrée mal attribuée se déplace, une fausse entrée se supprime, DEPUIS la revue :
  // c'est là qu'on les voit, et c'est là que la clôture est refusée à cause d'elles.
  {
    const th = { file: "RM42_x.think.md", counts: { questions_open: 1 }, blocking: true,
                 questions: [{ id: "Q001", icon: "❓", text: "vraie question ?", open: true }], decisions: [], features: [], notes: [] };
    const pane = String(V.ThinkPane(th));
    assert(/data-action="think-move" data-id="Q001"/.test(pane), "le volet Réflexion offre le déplacement");
    assert(/data-action="think-delete" data-id="Q001"/.test(pane), "…et la suppression");
    assert(!/onclick=/.test(pane), "gestes délégués, aucun on*");
    // RM3262 : la signature accompagne l'entrée, sans voler la vedette à son texte
    const signe = String(V.ThinkPane({ file: "f", counts: {}, decisions: [], features: [], notes: [],
      questions: [{ id: "Q001", icon: "❓", text: "vraie question ?", signature: "2026-09-01 · Mathieu", open: true }] }));
    assert(/class="thk-sig"[^>]*>2026-09-01 · Mathieu</.test(signe), "la question dit qui l'a posée, et quand");
    assert(signe.indexOf("vraie question ?") > signe.indexOf("thk-sig"), "…après l'id et la signature, le texte");
    assert(!/thk-sig/.test(String(V.ThinkPane({ file: "f", counts: {}, decisions: [], features: [], notes: [],
      questions: [{ id: "Q001", icon: "❓", text: "carnet pas encore migré", open: true }] }))), "sans signature connue : rien d'inventé");
    const closed = String(V.ThinkPane({ file: "f", counts: {}, questions: [{ id: "Q002", icon: "✅", text: "tranchée", closed: true }], decisions: [], features: [], notes: [] }));
    assert(!/think-move|think-delete/.test(closed), "une entrée déjà tranchée n'offre pas ces gestes");
  }
  {
    const vus = []; let reponse = "3015";
    const ctr2 = mountReview(fakeElement(), { ticket: T, service: svc, center, notify: (m, e) => ev.push(["toast", m, !!e]),
      confirm: () => true, prompt: () => reponse, resolve: () => resolve, cfg: () => CFG, show: () => {}, setMeta: () => {}, renderMeta: () => {},
      noteOpened: () => {}, showRight: () => {}, refreshSessions: () => {}, tq: { entry: () => null, loaded: () => false, size: () => 0, load: () => {} },
      launcher: () => ({ engine: "claude", model: "" }), popover: () => fakeElement(), place: () => {}, onOutsideClick: () => {},
      cdc: { thinkEdit: async (body) => { vus.push(body); return { ok: true }; } } });
    ctr2.open("42"); await settle();
    ev.length = 0;
    await ctr2.el.fire("click", "[data-action]", { dataset: { action: "think-move", id: "Q001" } }); await settle();
    assert.deepStrictEqual(vus[vus.length - 1], { rm: "42", id: "Q001", action: "move", to: "3015" }, "déplacer : le front dit l'entrée et la cible, rien d'autre");
    reponse = "RM77";
    await ctr2.el.fire("click", "[data-action]", { dataset: { action: "think-move", id: "Q001" } }); await settle();
    assert.strictEqual(vus[vus.length - 1].to, "77", "« RM77 » saisi à la main est accepté");
    reponse = "n'importe quoi"; const n0 = vus.length;
    await ctr2.el.fire("click", "[data-action]", { dataset: { action: "think-move", id: "Q001" } }); await settle();
    assert.strictEqual(vus.length, n0, "saisie invalide : rien ne part sur le réseau");
    assert(ev.some(x => x[0] === "toast" && x[2]), "…et on le dit");
    await ctr2.el.fire("click", "[data-action]", { dataset: { action: "think-delete", id: "N003" } }); await settle();
    assert.deepStrictEqual(vus[vus.length - 1], { rm: "42", id: "N003", action: "delete" }, "supprimer depuis la revue");
    ctr2.unmount();
  }
  console.log("✓ réflexion (RM3258/RM3064) : déplacer vers un autre ticket, supprimer, depuis la revue");
  ctr.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur : ouverture/fermeture/cession, consigne hors DOM, verdict, doublon rejoint, menu de statut");
  console.log("\nTous les tests de la revue passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
