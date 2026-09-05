// boot — pont de cohabitation entre le monolithe et les modules. RM2889, L0.
//
// Le `<script>` historique d'index.html n'est pas un module : il ne peut pas
// `import`. Pendant toute la migration, le socle lui est donc exposé sur
// `window.karl`, en un seul point, et le monolithe s'en sert progressivement —
// c'est ce qui permet de migrer un domaine à la fois sans jamais casser les
// autres (§ 15.1).
//
// Ordre d'exécution : un module est différé, il s'exécute donc APRÈS le script
// inline. Le monolithe ne doit pas lire `window.karl` au chargement, mais dans
// ses gestes — ou attendre l'événement `karl:ready`.
//
// Ce pont disparaît au lot L6, quand plus rien d'inline ne subsiste.

import { esc, jarg, html, raw, isSafe, attrs } from "./core/html.js";
import { Store, defineStore, storeStats, resetStores } from "./core/store.js";
import { mount, on, domStats } from "./core/dom.js";
import { ROUTES, route, targetRoute } from "./core/endpoints.js";
import { api, get, post, configureApi } from "./core/api.js";
import { AppError, ApiError, asAppError } from "./core/errors.js";
import { Repository } from "./models/Repository.js";
import { Factory } from "./models/Factory.js";
import { EntityViewModel, withConso } from "./viewmodels/EntityViewModel.js";
import { mountMailPanel } from "./controllers/mail.controller.js";
import { mountGitPanel } from "./controllers/git.controller.js";
import { mountDashboard } from "./controllers/dashboard.controller.js";
import { mountProjectsPanel } from "./controllers/projects.controller.js";
import { mountEnv } from "./controllers/env.controller.js";
import { mountPmCommands } from "./controllers/pmcmd.controller.js";
import { mountSettings } from "./controllers/settings.controller.js";
import { mountVoice } from "./controllers/voice.controller.js";
import { mountCenter } from "./controllers/center.controller.js";
import { mountNewTicket } from "./controllers/newticket.controller.js";
import { mountProject } from "./controllers/project.controller.js";
import { mountTestQueue } from "./controllers/testqueue.controller.js";
import { TicketRepository } from "./models/tickets/TicketRepository.js";
import * as TF from "./models/tickets/ticketFormat.js";
import { MergeBanner } from "./views/tickets/MergeBanner.view.js";
import { mountReview } from "./controllers/review.controller.js";
import { mountMeta } from "./controllers/meta.controller.js";
import { mountTicketsPanel } from "./controllers/tickets.controller.js";
import { mountDocModal } from "./controllers/doc.controller.js";
import { mountOutline } from "./controllers/outline.controller.js";
import { mountResume } from "./controllers/resume.controller.js";
import { mountSearch } from "./controllers/search.controller.js";
import { mountFiles } from "./controllers/files.controller.js";
import { mountWorklog } from "./controllers/worklog.controller.js";
import { mountLayout } from "./controllers/layout.controller.js";
import { mountLauncher } from "./controllers/launcher.controller.js";
import { mountSessionActions } from "./controllers/actions.controller.js";
import { mountTerminal } from "./controllers/terminal.controller.js";
import { mountSessions } from "./controllers/sessions.controller.js";
import { mountSets } from "./controllers/sets.controller.js";
import { mountRefresh } from "./controllers/refresh.controller.js";
import { mountAuth } from "./controllers/auth.controller.js";
import { effDisposition } from "./models/sessions/sessions.js";
import { MrLine } from "./views/worklog/Worklog.view.js";
import { mrLine } from "./viewmodels/worklog/WorklogViewModel.js";
import { mdToHtml } from "./core/markdown.js";
import { glossaireRows, glossaireFiltre } from "./models/glossary/glossary.js";
import { promptTemplates, taskPromptText, promptFillOnChange } from "./models/tickets/prompts.js";
import { fsScope, scopeTag } from "./models/files/scope.js";
import { FileViewModel } from "./viewmodels/center/CenterViewModels.js";
import { FileBody, centerBtnHtml } from "./views/center/Center.view.js";
import { GitPatch } from "./views/git/GitPanel.view.js";
import { GitPatchViewModel } from "./viewmodels/git/GitPatchViewModel.js";

// Le transport lit sa configuration dans les globaux du monolithe tant qu'il
// existe (CFG, token) — à la demande, jamais au chargement : CFG est rempli
// après le login. Le 401 reprend le geste historique : ré-afficher l'écran.
configureApi({
  get authRequired() { return !!(window.CFG && window.CFG.auth_required); },
  token: () => localStorage.getItem("karlToken") || "",
  onUnauthorized: () => {
    const g = document.getElementById("authgate");
    if (g) g.classList.add("show");
  },
});

const karl = Object.freeze({
  // rendu
  esc, jarg, html, raw, isSafe, attrs,
  // cache
  Store, defineStore, resetStores,
  // montage et cycle de vie
  mount, on,
  // routes nommées et transport
  ROUTES, route, targetRoute, api, get, post,
  // erreurs
  AppError, ApiError, asAppError,
  // classes de base
  Repository, Factory, EntityViewModel, withConso,
  /**
   * Ce que le front retient, en clair. Consultable depuis la console pendant
   * l'enquête RM2807 : `karl.stats()`. Devient un panneau d'interface en L1b.
   */
  stats() {
    const stores = storeStats();
    return {
      dom: domStats(),
      stores,
      entries: stores.reduce((n, s) => n + s.entries, 0),
      subscribers: stores.reduce((n, s) => n + s.subscribers, 0),
    };
  },
});

// — domaines migrés : chacun monte son panneau, avec le contexte que le
//   monolithe lui prête encore (toast, aide, ouverture au centre, badge de nav).
//   Ces ponts vers des globaux disparaissent domaine par domaine, jusqu'à L6. —
const legacy = (name) => (...a) => (typeof window[name] === "function" ? window[name](...a) : undefined);
// la modale doc : documents rendus (RM2309), aide intégrée (RM2593), glossaire du jargon (RM2623) — et les termes
// soulignés partout dans la page. Montée d'abord : tous les panneaux lui empruntent l'aide. Le routeur (center)
// est lu à l'appel, quand un document part au centre.
// la disposition (RM2466/2579/2599/2952) : colonnes repliables, onglets de droite, largeur, préférences. Montée d'abord : les
// domaines la lisent (rightVisible) ; ce qu'un onglet visible déclenche est décidé ici, après que tous sont montés (onApply lit
// les contrôleurs à l'appel, jamais au montage).
const layout = mountLayout({ main: document.querySelector("main"), lnav: document.querySelector(".lnav"), lbody: document.querySelector(".lbody"), rpanel: byId("rpanel"), rnav: document.querySelector("#rpanel .rnav"), rtoggle: byId("rtoggle"), ltoggle: byId("ltoggle"), rhandle: byId("rhandle"), startOpen: byId("rp-startopen"), defTab: byId("rp-deftab") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), root: document,
  onApply: (r, visible) => {
    const att = lexical(() => attached);
    if (visible("outline") && att) outlineCtl.load();                       // RM2330 : ne charge qu'une fois réellement visible
    if (visible("infos") && meta) meta.renderInfos();                       // RM2579 : (re)peuple l'onglet visible
    if (visible("tickets") && meta) meta.renderTickets();
    if (visible("state") && worklogCtl) worklogCtl.load();                  // RM2581
    if (visible("files") && files) files.ensure();                          // RM2586/2673 : compare le contexte, pas le seul sid
    if (visible("git") && att) git.refresh();                               // RM2602
  },
  onResized: () => terminal.fit(),   // le terminal (migré) se réajuste après un redimensionnement
  // RM2283/2760/2816 : les panneaux gauche à contenu serveur chargent à leur première activation (lus à l'appel, jamais au montage)
  panelLoaders: { sessions: () => { resume.load(); setsCtl.load(); }, test: () => testqueue.load(), mail: () => mail.refresh(), projects: () => projects.refresh() },
});
const doc = Object.assign(mountDocModal(byId("docmodal"), { root: document, openCenterFile: (src, wt, p) => center.openFile(src, wt, p) }), { glossaireRows, glossaireFiltre });
const mail = mountMailPanel(document.getElementById("lp-mail"), {
  notify: legacy("toast"),
  help: (t) => doc.openHelp(t),
  openCenter: legacy("openCenterMail"),
  badge: (n) => { const b = document.getElementById("ln-mail"); if (b) { b.textContent = n || ""; b.style.display = n ? "" : "none"; } },
});

// les `let` de premier niveau du script inline (attached, sessCache) sont dans
// la portée globale partagée, pas sur window : on les lit par leur nom, protégé.
const lexical = (fn) => { try { return fn(); } catch (e) { return undefined; } };
const git = mountGitPanel(document.getElementById("rp-git"), {
  notify: legacy("toast"),
  attached: () => lexical(() => attached),
  branchesOf: (sid) => lexical(() => ((sessCache[sid] || {}).registry || {}).branches) || [],
  openCenter: legacy("openCenterCommit"),
});
// openCenterCommit (domaine fichiers, prochain sous-lot) rend encore un patch : on lui prête la vue.
window.gitPatchHtml = (payload) => String(GitPatch(new GitPatchViewModel(payload)));

const dashboard = mountDashboard(document.getElementById("dashboard"), {
  notify: legacy("toast"),
  attach: legacy("attach"), openReview: legacy("openReview"),
  pull: () => refreshCtl.fetch(["dashboard"]),
  sessions: () => lexical(() => sessCache) || {},
  stale: () => [...refreshCtl.stale()],
  nameOf: legacy("tmuxNameOf"),
  // visible = le vide central est affiché et aucune session n'est attachée (RM2697)
  visible: () => { const ph = document.getElementById("placeholder"); return !!ph && ph.style.display !== "none" && !lexical(() => attached); },
  // RM2744 : dès qu'il y a du contenu, l'alignement passe en haut ; l'indice s'efface
  shown: (on, hasContent) => {
    const box = document.getElementById("dashboard"), hint = document.getElementById("ph-hint"), ph = document.getElementById("placeholder");
    if (box) box.style.display = on ? "" : "none";
    if (ph) ph.classList.toggle("dash-on", on);
    if (hint) hint.style.display = on && hasContent ? "none" : "";
  },
});

const projects = mountProjectsPanel(document.getElementById("lp-projects"), {
  notify: legacy("toast"), help: (t) => doc.openHelp(t),
  sessions: () => Object.values(lexical(() => sessCache) || {}),
  resolve: () => lexical(() => resolveCache) || {},
  clientContext: () => launcher.clientContext(),
  pin: (kind, key) => legacy("pinOf")(kind, key) || "",
  openProject: legacy("openProjectView"), openClient: legacy("openCenterClient"), openConf: legacy("openCenterConf"),
});

// santé du poste et verrous : la modale partagée (docmodal) lui est prêtée, comme
// le badge et le bouton d'en-tête — trois surfaces, un contrôleur.
const env = mountEnv(document.getElementById("doccontent"), {
  notify: legacy("toast"), clip: (txt) => terminal.writeClip(txt),   // presse-papier avec replis (terminal migré)
  pull: (block) => refreshCtl.fetch([block]),
  secure: () => !!window.isSecureContext,
  modal: (title, cls) => { const t = document.getElementById("doctitle"), c = document.getElementById("doccontent"), m = document.getElementById("docmodal");
    if (t) t.textContent = title; if (c) c.className = cls; if (m) m.classList.add("show"); },
  badge: (h) => { const el = document.getElementById("envwarn"); if (el) { el.innerHTML = h; el.style.display = h ? "" : "none"; } },
  lock: (s) => { const el = document.getElementById("lockbtn"); if (el) { el.style.display = s.show ? "" : "none"; el.textContent = s.label; el.title = s.title; } },
});

const pmcmd = mountPmCommands(document.getElementById("pmcard"), {
  notify: legacy("toast"), help: (t) => doc.openHelp(t), run: legacy("pmRun"),
});
const settings = mountSettings(document.getElementById("reglages-card"), document.getElementById("themecard"), {
  notify: legacy("toast"), help: (t) => doc.openHelp(t), applyTheme: legacy("applyTheme"),
  effectiveTheme: () => document.documentElement.getAttribute("data-theme"),
});

// la voix : les moteurs du navigateur sont fournis ICI, au seul endroit qui les connaît
const synth = () => (typeof speechSynthesis !== "undefined" ? speechSynthesis : null);
const voice = mountVoice(document.getElementById("voicecard"), {
  notify: legacy("toast"), storage: localStorage,
  attached: () => lexical(() => attached), resolve: () => lexical(() => resolveCache) || {},
  voiceBtn: (on) => { const b = document.getElementById("voicebtn"); if (b) { b.style.color = on ? "var(--ok)" : ""; b.style.borderColor = on ? "var(--ok)" : ""; } },
  mic: (s) => { const b = document.getElementById("micbtn"); if (b) { b.style.color = s.color; b.textContent = s.text; } },
  engines: {
    voices: () => (synth() ? synth().getVoices() : []),
    cancel: () => synth() && synth().cancel(),
    speak: (text, lang, v) => { const u = new SpeechSynthesisUtterance(text); u.lang = lang; if (v) u.voice = v; synth().speak(u); },
    audio: async (blob) => { let a = document.getElementById("tts-audio"); if (!a) { a = document.createElement("audio"); a.id = "tts-audio"; document.body.appendChild(a); }
      if (a.src) URL.revokeObjectURL(a.src); a.src = URL.createObjectURL(blob); await a.play(); },
    recognizer: (window.SpeechRecognition || window.webkitSpeechRecognition)
      ? (lang) => { const r = new (window.SpeechRecognition || window.webkitSpeechRecognition)(); r.lang = lang; r.interimResults = false; r.maxAlternatives = 1; return r; } : null,
    recorder: (navigator.mediaDevices && window.MediaRecorder) ? async () => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      let mr; try { mr = new MediaRecorder(stream); } catch (e) { stream.getTracks().forEach(t => t.stop()); return null; }
      const chunks = []; const h = { onstop: null,
        start: () => mr.start(), stop: () => mr.stop() };
      mr.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunks.push(ev.data); };
      mr.onstop = () => { stream.getTracks().forEach(t => t.stop()); if (h.onstop) h.onstop(new Blob(chunks, { type: (chunks[0] && chunks[0].type) || "audio/webm" })); };
      return h; } : null,
  },
});

// ── le centre : routeur des onglets, de l'historique, du titre et des vues ─────
// Les surfaces encore historiques (session, revue, fiche projet, nouveau ticket)
// sont ENREGISTRÉES ici comme des ponts. Migrer l'une d'elles remplacera son pont.
const byId = (id) => document.getElementById(id);
const show = (id, on, mode = "block") => { const el = byId(id); if (el) el.style.display = on ? mode : "none"; };
let project = null, review = null, testqueueRef = null, meta = null, tickets = null, files = null, worklogCtl = null, launcher = null, terminal = null, sessionsCtl = null, setsCtl = null, refreshCtl = null, auth = null;
const centerCore = mountCenter({ tabs: byId("ctabs"), hist: byId("histbox"), view: byId("viewpane"), title: byId("curtitle") }, {
  storage: localStorage, notify: legacy("toast"), notifyAction: legacy("toastAction"), md: mdToHtml,
  resolve: () => lexical(() => resolveCache) || {},
  scope: () => ({ filesData: files.data(), attached: lexical(() => attached), projectKey: project ? project.current() : null }),
  surfaces: {
    session:   { sessions: () => lexical(() => sessCache) || {}, list: async () => (await get(route("session.sessions")) || {}).sessions || [],
                 open: legacy("attach"), relaunch: (s) => setsCtl.relaunchGhost(s), close: () => { if (lexical(() => attached)) legacy("detach")(); } },
  },
  panels: {
    pm:       { label: "commandes pm", load: () => pmcmd.load(),    show: (on) => show("cp-pm", on) },
    settings: { label: "réglages",     load: () => settings.load(), show: (on) => show("cp-settings", on) },
  },
  panelShow: (on) => show("panelpane", on), viewShow: (on) => show("viewpane", on),
  placeholder: (on) => show("placeholder", on, "flex"),
  dashboard: () => dashboard.refresh(),
  nothingElse: () => !lexical(() => attached) && !(review && review.current()) && !(project && project.current()),
  histOpen: () => { const b = byId("histbox"); return !!b && b.style.display !== "none"; },
  histShow: (on) => show("histbox", on),
  navButtons: ({ back, fwd }) => { const b = byId("histback"), f = byId("histfwd"); if (b) b.disabled = !back; if (f) f.disabled = !fwd; },
  legacyTitle: () => (sessionsCtl ? sessionsCtl.titleHtml() : "") || (review && review.current() ? review.titleHtml((rm, tt) => legacy("titleLink")(rm, tt) || "") : "") || (project ? project.titleHtml() : ""),
  afterTitle: () => { if (sessionsCtl) sessionsCtl.afterTitle(); },   // RM2894/2302/2327 : en-tête droit, « ✔ Oui », auto-oui suivent la vue
  // RM2795 : les listes portent la même marque d'épinglage — elles se redessinent au geste
  onPinChange: () => { try { legacy("renderOpened")(); } catch (e) {} projects.render(); if (worklogCtl && worklogCtl.data().found) worklogCtl.render(); try { refreshCtl.refreshSessions(); } catch (e) {} },
});
const center = Object.assign(centerCore, {
  scopeTagOf: (wt) => scopeTag(fsScope(wt, files.data(), lexical(() => attached), project ? project.current() : null)),
  fileBodyHtml: (f) => String(FileBody(new FileViewModel(f, { md: mdToHtml }))),
  centerBtn: centerBtnHtml,
});
// première surface migrée : elle remplace son pont. RM2726 : la cible par défaut
// est celle du lanceur éclair (#nt-project), elle-même posée par le contexte client.
const newticket = mountNewTicket(byId("ntpane"), {
  center, notify: legacy("toast"), openReview: legacy("openReview"),
  show: (on) => show("ntpane", on),
  config: () => ({ types: (lexical(() => CFG) || {}).task_types || [], priorities: (lexical(() => CFG) || {}).priorities || [] }),
  projects: () => launcher.projects(),
  defaultTarget: () => { const cur = ((byId("nt-project") || {}).value || "").split("/"); return { client: cur[0] || launcher.clientContext(), project: cur[1] || "" }; },
});
center.register("newticket", { open: newticket.open, close: newticket.close });
// la fiche projet : deuxième surface enregistrée
project = mountProject(byId("projpane"), {
  center, notify: legacy("toast"), run: legacy("pmRun"),
  show: (on) => show("projpane", on),
  sessions: (key) => (sessionsCtl ? sessionsCtl.groups() : {})[key] || [],
  attach: legacy("attach"), showTicket: legacy("showTicket"), openDoc: legacy("openDoc"),
  titleLink: (rm, t) => legacy("titleLink")(rm, t) || "", ago: legacy("ago"),
  mrLine: (m) => String(MrLine(mrLine(m))), mergeMr: (url, iid, target, btn) => worklogCtl && worklogCtl.mergeOne(url, iid, target, btn),   // RM2723 : rendu et geste partagés avec le worklog de session
  fileBody: (f) => center.fileBodyHtml(f),
  filesEnsure: () => { if (layout.rightVisible("files")) legacy("filesEnsure")(); },
});
center.register("project", { open: project.open, close: () => { if (project.current()) project.close(); } });
// le modèle ticket : la logique dans le module, les caches partagés PAR RÉFÉRENCE avec le
// monolithe (une soixantaine de vues les lisent encore en direct — L6 les rapatriera)
const ticketRepo = new TicketRepository({ caches: { resolve: lexical(() => resolveCache), resolveAt: lexical(() => resolveAt), mc: lexical(() => mcCache), usage: lexical(() => usageCache), ts: lexical(() => tsCache) } });
// RM2775 : un titre arrivé après coup atteint l'infobulle de son onglet — seulement si un onglet le porte
const onResolved = (rm) => { if (center.hasTab(rm, ["review", "session"])) center.renderTabs(); };
const ticket = {
  stale: (rm) => ticketRepo.stale(rm),
  inFlight: (rm) => !!ticketRepo.inflight.resolve[String(rm)],   // RM2807 : garde anti fan-out des listes du monolithe
  ensureResolved: (rm, force) => ticketRepo.ensureResolved(rm, force, onResolved),
  revalidate: (rm, after) => ticketRepo.revalidate(rm, after, onResolved),
  /** Rechargement explicite (⟳) : recharge, puis re-rend ce que le monolithe affiche encore. */
  reload: (rm) => ticketRepo.ensureResolved(String(rm), true, onResolved).then(() => {
    rm = String(rm);
    if (meta && meta.ticketIs(rm)) meta.render();
    if (review && review.current() === rm) review.render();
    if (launcher && launcher.rm() === rm) launcher.resolve();
    legacy("toast")("RM" + rm + " rechargé");
  }),
  mcFresh: (rm) => ticketRepo.mcFresh(rm), ensureMergecheck: (rm, f) => ticketRepo.ensureMergecheck(rm, f),
  usageFresh: (rm) => ticketRepo.usageFresh(rm), usageInFlight: (rm) => ticketRepo.usageInFlight(rm), ensureUsage: (rm, f) => ticketRepo.ensureUsage(rm, f),
  ensureTicketSessions: (rm, f) => ticketRepo.ensureTicketSessions(rm, f),
  busySessions: (p) => TF.ticketBusySessions(p, effDisposition),
  mcBanner: (mc) => String(MergeBanner(mc)),
  sinceLabel: TF.sinceLabel, modelWindow: TF.modelWindow, ctxPct: TF.ctxPct, throughput: TF.throughput, fmtUsd: TF.fmtUsd, fmtRate: TF.fmtRate, fmtWin: TF.fmtWin,
  repo: ticketRepo,
};
// l'onglet 🗺 conversation (RM2330/2549/2596/2601) : la session attachée, les toasts, les refs cliquables (linkify) sont prêtés
const outlineCtl = mountOutline({ body: byId("outbody"), count: byId("outcnt"), nav: document.querySelector("#rp-outline .outnav") }, {
  attached: () => lexical(() => attached), notify: legacy("toast"), linkify: (s) => legacy("linkify")(s) || "", clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
});
// la carte « Reprendre une session » (RM1939/2834/2991/2418) : projets connus, contexte client, lanceur, attache et suites d'une reprise prêtés
const resume = mountResume(byId("rescard"), {
  notify: legacy("toast"), ago: legacy("ago"), markPill: (m) => legacy("markPillHtml")(m) || "", projects: () => launcher.projects(),
  launcherRm: () => (byId("rm") || {}).value || "", attach: legacy("attach"),
  afterResume: async (r) => { setsCtl.warnSpawn(r); await refreshCtl.refreshSessions(); refreshCtl.refreshHealth(); },
});
// l'onglet 📂 fichiers (RM2586/2622/2659/2673/2675/2759/2861) : le contexte de lecture (session, fiche de ticket, fiche projet,
// jeu courant), le rendu commun d'un fichier, la portée d'un worktree et l'ouverture au centre sont prêtés
files = mountFiles({ body: byId("filesbody"), count: byId("filescnt"), nav: document.querySelector("#rp-files .outnav") }, {
  notify: legacy("toast"), attached: () => lexical(() => attached), resolve: () => lexical(() => resolveCache) || {},
  reviewCurrent: () => (review ? review.current() : null), projectKey: () => (project ? project.current() : null),
  sets: () => setsCtl.sets(), currentSet: () => setsCtl.current(),
  fileBody: (f) => String(FileBody(new FileViewModel(f, { md: mdToHtml }))), scopeTagOf: (wt) => center.scopeTagOf(wt), showRight: layout.showRight,
  center: { openFile: (src, wt, p, tag) => center.openFile(src, wt, p, tag), openDir: (src, wt, p, tag) => center.openDir(src, wt, p, tag), openCommit: (sid, hash) => center.openCommit(sid, hash) },
});
// le panneau 🎫 tickets (RM1952 triage, RM2606 tickets ouverts, RM2619 infobulles) : le monolithe prête les résolutions,
// la fiche ℹ (meta), l'épinglage, le contexte client et le chemin partagé de lancement d'un lot (RM2823/2831)
tickets = mountTicketsPanel({ triage: byId("triagecard"), opened: byId("openedcard"), badge: byId("ln-tickets") }, {
  ticket, notify: legacy("toast"), storage: (typeof localStorage !== "undefined" ? localStorage : null), root: document,
  resolve: () => lexical(() => resolveCache) || {}, showTicket: (id) => meta && meta.showTicket(id), pinOf: (k, key) => center.pinOf(k, key),
  clientContext: () => launcher.clientContext(), spawnBatch: (items, btn, opts) => worklogCtl.spawnBatch(items, btn, opts),
});
// la recherche de tickets (RM2770/2639/2830) : projets connus, contexte client, statuts NORMS, lien de titre, épinglage prêtés ;
// un résultat cliqué prépare le lanceur, une étiquette chargée alimente aussi le menu du triage
const search = mountSearch(byId("searchcard"), {
  notify: legacy("toast"), projects: () => launcher.projects(), clientContext: () => launcher.clientContext(),
  statuses: () => ((lexical(() => CFG) || {}).statuses) || [], redmineBase: () => ((lexical(() => CFG) || {}).redmine_url) || "",
  titleLink: (rm, tt) => legacy("titleLink")(rm, tt) || "", pinOf: (k, key) => center.pinOf(k, key),
  pick: (rm) => launcher.setRm(rm, { switchPanel: true, scroll: true }),   // RM2283 : le lanceur vit dans « sessions »
  openExternal: (url) => window.open(url, "_blank", "noopener"), onTags: (tags) => tickets.setTags(tags),
});
// l'onglet 🗒 worklog et ses lots (RM2466/2581/2716/2720/2723/2786/2823/2831) : la session attachée, le registre, CFG, le runner PM,
// la capture, la modale doc (écrans de lot), l'infobulle, la marque, linkify, la revue, la fiche ℹ, le lanceur et l'attache sont prêtés
worklogCtl = mountWorklog({ body: byId("workbody"), fresh: byId("workfresh"), nav: document.querySelector("#rp-state .outnav") }, {
  ticket, notify: legacy("toast"), ago: legacy("ago"), run: legacy("pmRun"), capture: (t, txt) => doc.openPlain(t, txt),
  attached: () => lexical(() => attached), sess: () => lexical(() => sessCache) || {}, cfg: () => lexical(() => CFG) || {}, resolve: () => lexical(() => resolveCache) || {},
  tipAttr: (id) => tickets.tipAttr(id), pinOf: (k, key) => center.pinOf(k, key), linkify: (s) => legacy("linkify")(s) || "",
  openReview: (rm) => review.open(rm), openStatusMenu: (ref, n, e) => review.openStatusMenu(ref, n, e), showTicket: (rm) => meta && meta.showTicket(rm),
  modal: { open: (t, f, on) => doc.openCustom(t, f, on), close: () => doc.closeDoc(), content: () => doc.contentEl() },
  launcher: () => ({ engine: (byId("engine") || {}).value || "claude", model: (byId("model") || {}).value || "" }),
  warnSpawn: (r) => setsCtl.warnSpawn(r), refreshSessions: (() => refreshCtl.refreshSessions()), attach: legacy("attach"), forgetOpened: (rm) => tickets.forget(rm),
  forgetTicketSessions: (rm) => { const c = lexical(() => tsCache); if (c) c[rm] = undefined; },
  openExternal: (u) => window.open(u, "_blank", "noopener"), projectWorklog: () => project && project.refreshWorklog(),
  afterLoad: () => { if (layout.rightVisible("tickets") && meta) meta.renderTickets(); },   // RM2673 : le worklog alimente la liste des tickets
});
// les actions d'une session (RM1893 §2 chips, RM2720 actions PM d'un ticket, §3 moniteurs, RM2515 disposition, fermeture) :
// la session attachée, le registre, CFG, le détachement et les rafraîchissements sont prêtés
const actions = mountSessionActions({ chips: byId("chipsrow"), bar: byId("tabactions") }, {
  notify: legacy("toast"), attached: () => lexical(() => attached), sess: () => lexical(() => sessCache) || {}, cfg: () => lexical(() => CFG) || {},
  detach: legacy("detach"), refreshSessions: (() => refreshCtl.refreshSessions()), refreshHealth: (() => refreshCtl.refreshHealth()),
  popover: () => { const m = document.createElement("div"); m.className = "dispmenu"; m.id = "dispmenu"; document.body.appendChild(m); return m; },
  place: (m, anchor) => { const r = anchor.getBoundingClientRect(); m.style.left = Math.round(Math.min(r.left, window.innerWidth - m.offsetWidth - 6)) + "px"; m.style.top = Math.round(r.bottom + 4) + "px"; },
  onOutsideClick: (fn) => setTimeout(() => document.addEventListener("click", fn, { once: true }), 0),
});
// le terminal de la session attachée (RM2522 client maison opt-in / iframe ttyd, RM2700 cookie de gate, RM2807 sonde) et le composer
// (RM2527 garde d'état, historique de ce navigateur), copies RM2168/2631 : CFG, le token, l'état live des sessions et la modale texte sont prêtés
terminal = mountTerminal({ host: byId("termhost"), frame: byId("term"), composer: byId("composer") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), win: window, cfg: () => lexical(() => CFG) || {}, notify: legacy("toast"),
  attached: () => lexical(() => attached), sess: () => lexical(() => sessCache) || {}, token: () => auth.token(),
  setCookie: (c) => { document.cookie = c; }, clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
  copyFallback: (txt) => { const ta = document.createElement("textarea"); ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.focus(); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; } ta.remove(); return ok; },
  capture: (t, txt) => doc.openPlain(t, txt), domCount: () => document.getElementsByTagName("*").length,
});
// la revue : troisième surface enregistrée. Le monolithe lui prête l'encart ℹ, les sessions,
// l'attache, le lanceur (moteur/modèle), la recherche par étiquette, les actions PM.
review = mountReview(byId("reviewpane"), {
  center, ticket, run: legacy("pmRun"), notify: legacy("toast"), capture: (t, txt) => doc.openPlain(t, txt), md: mdToHtml,
  titleLink: (rm, tt) => legacy("titleLink")(rm, tt) || "", eff: effDisposition,
  resolve: () => lexical(() => resolveCache) || {}, cfg: () => lexical(() => CFG) || {},
  show: (on) => show("reviewpane", on),
  setMeta: (rm) => meta && meta.setTicket(rm), metaIs: (rm) => !!(meta && meta.ticketIs(rm)), renderMeta: () => meta && meta.render(),
  noteOpened: (rm) => tickets.noteOpened(rm), showRight: layout.showRight, refreshSessions: (() => refreshCtl.refreshSessions()),
  filesEnsure: () => { if (layout.rightVisible("files")) legacy("filesEnsure")(); },
  afterStatus: (rm) => { if (launcher && launcher.rm() === String(rm)) launcher.resolve(); if (lexical(() => attached) && layout.rightVisible("state")) worklogCtl.load(true); },
  attach: legacy("attach"), warnSpawn: (r) => setsCtl.warnSpawn(r), filterByTag: legacy("filterByTag"),
  pmTarget: (rm) => actions.pmTarget(rm),
  sendPmAction: (idx, rm, btn) => actions.sendPmAction(idx, rm, btn),
  launcher: () => ({ engine: (byId("engine") || {}).value || "claude", model: (byId("model") || {}).value || "" }),
  tq: { entry: (rm) => testqueueRef && testqueueRef.entry(rm), loaded: () => !!(testqueueRef && testqueueRef.loaded()), size: () => (testqueueRef ? testqueueRef.size() : 0), load: () => testqueueRef && testqueueRef.load(),
        deploy: (rm, b) => testqueueRef && testqueueRef.deploy(rm, b), teardown: (rm, b) => testqueueRef && testqueueRef.teardown(rm, b), deployShared: (rm, b) => testqueueRef && testqueueRef.deployShared(rm, b) },
  // le menu de statut : un popover posé sur le body, ancré sous la pastille
  popover: () => { const m = document.createElement("div"); m.className = "dispmenu"; m.id = "stmenu"; document.body.appendChild(m); return m; },
  place: (m, anchor) => { const r = anchor.getBoundingClientRect(); m.style.left = Math.round(Math.max(6, Math.min(r.left, window.innerWidth - m.offsetWidth - 6))) + "px"; m.style.top = Math.round(r.bottom + 4) + "px"; },
  onOutsideClick: (fn) => document.addEventListener("click", fn, { once: true }),
});
Object.assign(review, { taskPromptText, promptFillOnChange, promptTemplateOptions: (sel) => promptTemplates().map(t => `<option value="${esc(t.value)}"${t.value === String(sel == null ? "" : sel) ? " selected" : ""}>${esc(t.label)}</option>`).join("") });
center.register("review", { open: review.open, close: () => { if (review.current()) review.close(); } });
// le lanceur (§1 résolution, RM1941 modèles, RM2873 consigne, RM2818 garde, spawn), la saisie éclair d'un ticket (§8) et le contexte
// client (RM2639) : CFG, la consigne et la garde (revue), le runner PM, l'attache et les suites sont prêtés ; le contexte prévient le reste
launcher = mountLauncher({ card: byId("launchcard"), ntcard: byId("ntcard"), clientctx: byId("clientctx") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), cfg: () => lexical(() => CFG) || {}, notify: legacy("toast"), capture: (t, txt) => doc.openPlain(t, txt), run: legacy("pmRun"),
  promptText: taskPromptText, promptFill: promptFillOnChange, confirmSecondSession: (rm) => review.confirmSecondSession(rm), warnSpawn: (r) => setsCtl.warnSpawn(r),
  afterSpawn: async () => { await refreshCtl.refreshSessions(); refreshCtl.refreshHealth(); }, attach: legacy("attach"), switchPanel: (n) => layout.switchPanel(n),
  afterStatus: async (rm) => { await ticket.ensureResolved(rm, true); if (meta && meta.ticketIs(rm)) meta.render(); if (review.current() === rm) review.render(); },   // RM2229 : re-résout partout
  afterCreate: () => search.refreshIfQuery(),
  onProjects: () => { resume.setProjects(); search.loadTags(); search.init(); },                    // RM2834/2830/2770
  onContext: (c, proj, initial) => { legacy("setClientCtxLocal")(c); tickets.filterClient(c || null); resume.applyClientContext(c, proj);   // RM2639 : le reste du cockpit suit
    if (!initial) { search.refreshIfQuery(); projects.render(); search.fillProjects(); refreshCtl.refreshSessions(); } },
});
// RM2873 : le lanceur de gauche propose les mêmes modèles de consigne que la fiche
{ const sel = byId("ptpl"); if (sel) sel.innerHTML = review.promptTemplateOptions("traiter"); }
// l'encart ℹ (RM2173/2579/2605/2614/2673/2797) : colonne de droite « infos » + « tickets ». Le monolithe
// lui prête la session attachée, le registre, les caches ticket, le worklog, la colonne et les gestes voisins.
meta = mountMeta({ infos: byId("infosbody"), tickets: byId("ticketsbody") }, {
  ticket, notify: legacy("toast"), md: mdToHtml, ago: legacy("ago"), tipAttr: (id) => tickets.tipAttr(id),
  resolve: () => lexical(() => resolveCache) || {}, sess: () => lexical(() => sessCache) || {}, usage: () => lexical(() => usageCache) || {},
  attached: () => lexical(() => attached), worklog: () => worklogCtl.data(), worklogPending: () => worklogCtl.pending(), loadWorklog: () => worklogCtl.load(),
  showRight: layout.showRight, noteOpened: (id) => tickets.noteOpened(id), gotoTicket: (rm) => launcher.goto(rm), reopen: (rm) => launcher.reopen(rm),
  openReview: (rm) => review.open(rm), reload: (rm) => ticket.reload(rm), openStatusMenu: (rm, anchor, ev) => review.openStatusMenu(rm, anchor, ev), openProject: (key) => project.open(key),
  clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
});
// la file « à tester » : panneau de gauche autonome ; la revue lit ses entrées et lui emprunte ses gestes d'env
const testqueue = testqueueRef = mountTestQueue(byId("tqcard"), {
  notify: legacy("toast"), help: (t) => doc.openHelp(t), run: legacy("pmRun"), capture: (t, txt) => doc.openPlain(t, txt),
  resolveRefresh: (rm) => legacy("ensureResolved")(String(rm), true),
  openReview: (rm) => review.open(rm), verdict: (rm, k, b) => review.verdict(rm, k, b), pin: (k, key) => center.pinOf(k, key),
  afterLoad: () => { if (review.current()) review.render(); },
});
// la liste « en cours » (RM2283/2346/2427/2445/2448/2515/2598/2639/2787/2793/2210) et les raccourcis Oui / auto-oui (RM2302/2327/2332),
// le titre de la session attachée et l'en-tête droit (RM2894) : le registre live est PARTAGÉ par référence (sessCache) ; le monolithe prête
// l'attache, les questions sans réponse, la sélection et les jeux (état, setWritable/setLabel, ⊖ ⟳ relance), titleLink et la pile /refresh
sessionsCtl = mountSessions({ list: byId("runlist"), counters: byId("hcnt"), navCount: byId("ln-count"), navAtt: byId("ln-att"), yesAll: byId("yesall"), yesAtt: byId("yesatt"), yesBtn: byId("yesbtn"), autoYes: byId("autoyes"), title: byId("curtitle"), rtitle: byId("rtitle"), dynsort: byId("dynsort") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: legacy("toast"), ticket,
  caches: { sess: lexical(() => sessCache) }, resolve: () => lexical(() => resolveCache) || {}, attached: () => lexical(() => attached), stale: () => refreshCtl.stale(),
  selection: () => setsCtl.selection(), sets: () => ({ sets: setsCtl.sets(), current: setsCtl.current(), view: setsCtl.view() }),
  writable: (sets, name, view) => setsCtl.writable(sets, name, view), setLabel: (name) => setsCtl.label(name),
  clientContext: () => launcher.clientContext(), setClientContext: (c) => launcher.setClientContext(c),
  pin: (k, key) => center.pinOf(k, key), titleLink: (rm, tt) => legacy("titleLink")(rm, tt) || "",
  composerRefresh: () => terminal.composerRefresh(), attach: legacy("attach"), detach: legacy("detach"), refresh: (() => refreshCtl.refreshSessions()),
  kill: (rm) => actions.kill(rm), openDispositionMenu: (s, anchor) => actions.openDispositionMenu(s, anchor),
  drop: (s) => setsCtl.dropFromSet(s), relaunch: (s) => setsCtl.relaunchGhost(s), forget: (s) => setsCtl.forgetGhost(s), toggleRestart: (s) => setsCtl.toggleRestart(s),
  openProject: (key) => project.open(key), review: { tabs: () => review.tabs(), current: () => review.current(), open: (rm) => review.open(rm), close: (rm) => review.close(rm) },
  projectsVisible: () => { const p = byId("lp-projects"); return !!p && p.classList.contains("active"); }, renderProjects: () => projects.render(),
  announce: (sessions) => voice.announce(sessions), renderTitle: () => center.title(), docTitle: (t) => { document.title = t; },
});
// les jeux de sessions (RM2395/2442/2445/2446/2448/2449/2451/2452/2673/2741/2955) : barre du panneau « en cours » et carte « Sessions enregistrées » ;
// la liste migrée prête les sessions AFFICHÉES, le monolithe le toast (simple et avec action), confirm/prompt, l'attache et la pile /refresh
setsCtl = mountSets({ bar: byId("setbar"), card: byId("sessions-set-card") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: legacy("toast"), notifyAction: legacy("toastAction"),
  confirm: (m) => window.confirm(m), prompt: (m, d) => window.prompt(m, d),
  ordered: () => sessionsCtl.ordered(), refreshSessions: (() => refreshCtl.refreshSessions()), attach: legacy("attach"),
});
// la pile /refresh (RM2763 composite unique, RM2613 cadence adaptative), la pastille de santé, « ⬆ MAJ dispo » (RM2571) et les questions
// sans réponse (RM2598) : les blocs reçus vont aux domaines migrés ; les caches de résolution sont partagés par référence ; le premier tick
// est déclenché par l'init du monolithe (tickSessions) une fois la configuration connue
refreshCtl = mountRefresh({ health: byId("health"), healthtxt: byId("healthtxt"), updbtn: byId("updbtn") }, {
  caches: { resolve: lexical(() => resolveCache), resolveAt: lexical(() => resolveAt) }, root: document, alert: (t) => window.alert(t),
  attached: () => lexical(() => attached), worklogVisible: () => layout.rightVisible("state"), dashboardVisible: () => dashboard.visible(),
  onSessions: (list) => sessionsCtl.render(list), onWorklog: (d) => worklogCtl.setFromRefresh(d), onDashboard: (d) => dashboard.setBlock(d), onEnv: (k, d) => env.setBlock(k, d),
});
// l'authentification (RM2334) : écran de login plein-cadre, cadenas, carte de session et appareils, comptes (superadmin). L'init du monolithe
// appelle `boot` une fois CFG connu ; une connexion relance la santé et les sessions et ramène au panneau « en cours »
auth = mountAuth({ gate: byId("authgate"), card: byId("authcard"), users: byId("userscard"), lock: byId("lock") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), cfg: () => lexical(() => CFG) || {}, notify: legacy("toast"),
  confirm: (m) => window.confirm(m), prompt: (m) => window.prompt(m), ua: (typeof navigator !== "undefined" ? navigator.userAgent : ""),
  afterAuth: () => { refreshCtl.refreshHealth(); refreshCtl.refreshSessions(); }, switchPanel: (n) => layout.switchPanel(n),
});
// la disposition d'abord (repli des colonnes, onglet de droite, largeur — RM2466/2579/2599), puis les onglets épinglés — jamais une session
layout.restore();
center.restore();

window.karl = Object.freeze({ ...karl, mail, git, dashboard, projects, env, pmcmd, settings, voice, center, newticket, project, testqueue, ticket, review, meta, tickets, doc, outline: outlineCtl, resume, search, files, worklog: worklogCtl, layout, launcher, actions, terminal, sessions: sessionsCtl, sets: setsCtl, refresh: refreshCtl, auth });
window.dispatchEvent(new CustomEvent("karl:ready", { detail: window.karl }));
