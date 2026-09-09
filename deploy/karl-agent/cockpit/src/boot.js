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

import { html, raw, isSafe, attrs } from "./core/html.js";
import { Store, defineStore, storeStats, resetStores, appStores } from "./core/store.js";
import { createProbe } from "./core/probe.js";
import { mountMemory } from "./modules/memory/memory.controller.js";
import { mount, on, domStats, domStatsByModule, paint } from "./core/dom.js";
import { ROUTES, route, targetRoute } from "./core/endpoints.js";
import { api, get, post, configureApi } from "./core/api.js";
import { AppError, ApiError, asAppError } from "./core/errors.js";
import { Repository } from "./core/Repository.js";
import { Factory } from "./core/Factory.js";
import { EntityViewModel, withConso } from "./core/EntityViewModel.js";
import { mountMailPanel } from "./modules/mail/mail.controller.js";
import { mountGitPanel } from "./modules/git/git.controller.js";
import { mountDashboard } from "./modules/dashboard/dashboard.controller.js";
import { mountProjectsPanel } from "./modules/projects/projects.controller.js";
import { mountEnv } from "./modules/env/env.controller.js";
import { mountPmCommands } from "./modules/pmcmd/pmcmd.controller.js";
import { mountSettings } from "./modules/settings/settings.controller.js";
import { mountVoice } from "./modules/voice/voice.controller.js";
import { mountCenter } from "./modules/center/center.controller.js";
import { mountNewTicket } from "./modules/newticket/newticket.controller.js";
import { mountProject } from "./modules/projects/project.controller.js";
import { mountTestQueue } from "./modules/testqueue/testqueue.controller.js";
import { TicketRepository } from "./modules/ticket/TicketRepository.js";
import * as TF from "./modules/ticket/ticketFormat.js";
import { MergeBanner } from "./modules/ticket/MergeBanner.view.js";
import { mountReview } from "./modules/review/review.controller.js";
import { mountMeta } from "./modules/meta/meta.controller.js";
import { mountTicketsPanel } from "./modules/tickets/tickets.controller.js";
import { mountDocModal } from "./modules/doc/doc.controller.js";
import { mountOutline } from "./modules/outline/outline.controller.js";
import { mountResume } from "./modules/resume/resume.controller.js";
import { mountSearch } from "./modules/search/search.controller.js";
import { mountFiles } from "./modules/files/files.controller.js";
import { mountWorklog } from "./modules/worklog/worklog.controller.js";
import { mountLayout } from "./modules/layout/layout.controller.js";
import { MOBILE_MAX_PX } from "./modules/layout/mobile.js";
import { mountLauncher } from "./modules/launcher/launcher.controller.js";
import { mountSessionActions } from "./modules/actions/actions.controller.js";
import { mountTerminal } from "./modules/terminal/terminal.controller.js";
import { mountSessions } from "./modules/sessions/sessions.controller.js";
import { mountSets } from "./modules/sets/sets.controller.js";
import { mountRefresh } from "./modules/refresh/refresh.controller.js";
import { mountAuth } from "./modules/auth/auth.controller.js";
import { mountNotify } from "./modules/shell/notify.controller.js";
import { VERSION } from "./core/version.js";
import { createLog, installGlobalCapture, errorBrief } from "./core/log.js";
import { mountJournal } from "./modules/journal/journal.controller.js";
import { mountCdc } from "./modules/cdc/cdc.controller.js";                 // RM3044
import { mountClientNotify } from "./modules/clientnotify/clientnotify.controller.js";   // RM3052
import { mountSessProj } from "./modules/sessproj/sessproj.controller.js";   // RM3045
import { mountLinks } from "./modules/shell/links.controller.js";
import { mountAttach } from "./modules/shell/attach.controller.js";
import { mountCommands } from "./modules/shell/commands.controller.js";
import { PmService } from "./modules/pm/pm.service.js";
import { ago } from "./modules/sessions/sessions.js";
import { entryLabel } from "./modules/sets/sets.js";
import { effDisposition } from "./modules/sessions/sessions.js";
import { MrLine } from "./modules/worklog/Worklog.view.js";
import { mrLine } from "./modules/worklog/WorklogViewModel.js";
import { mdToHtml } from "./core/markdown.js";
import { glossaireRows, glossaireFiltre } from "./modules/doc/glossary.js";
import { promptTemplates, taskPromptText, promptFillOnChange } from "./modules/ticket/prompts.js";
import { fsScope, scopeTag } from "./modules/files/scope.js";
import { FileViewModel } from "./modules/center/CenterViewModels.js";
import { FileBody, centerBtnHtml } from "./modules/center/Center.view.js";

// La configuration d'instance (/cockpit-config, chargée par init) et les stores partagés entre domaines vivent ici — le script inline
// a disparu (L6). CFG est rempli après le login ; le transport le lit à la demande, jamais au chargement.
const CFG = { ttyd_base: "", auth_required: false, monitors: [], layouts: [], actions: [] };
const stores = appStores();   // RM3005 : les caches partagés sont des stores nommés et bornés (core/store.js), visibles dans karl.stats()
let auth = null, attachCtl = null;
// RM3011 : le journal du front — mêmes sévérités et catégories que le serveur ; warn/error remontés par POST /api/log/write ; les exceptions
// non rattrapées et les promesses rejetées y tombent. Créé AVANT tout montage : le premier domaine qui trébuche est déjà consigné.
const log = createLog({ remote: (rec) => post(route("log.write"), rec), version: VERSION, ua: (typeof navigator !== "undefined" ? navigator.userAgent : "") });
installGlobalCapture(log, window);
configureApi({
  get authRequired() { return !!CFG.auth_required; },
  token: () => (auth ? auth.token() : (localStorage.getItem("karlToken") || "")),
  onUnauthorized: () => { if (auth) auth.showGate(); },   // 401 : l'écran de login revient (RM2334)
});

// RM3007 : la sonde mémoire — un échantillon = DOM par module + stores + tas JS (Chromium seulement) ; rien ne tourne tant que
// la préférence « sonde » de ce navigateur n'est pas posée (réglages). Le panneau 🧠 mémoire la pilote.
const probe = createProbe({ sample: () => ({ dom: domStatsByModule(), stores: storeStats(), heap: (typeof performance !== "undefined" && performance.memory) ? performance.memory.usedJSHeapSize : null }) });

const karl = Object.freeze({
  // rendu
  html, raw, isSafe, attrs,
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
      modules: domStatsByModule(),                 // RM3007 : ventilé par module
      probe: probe.latest,                         // dernier échantillon de la sonde (null si désactivée)
      push: refreshCtl ? refreshCtl.push.state() : null,   // RM3006 : le canal de push (vivant ? blocs ? compteurs)
      stores,
      entries: stores.reduce((n, s) => n + s.entries, 0),
      subscribers: stores.reduce((n, s) => n + s.subscribers, 0),
    };
  },
});

const byId = (id) => document.getElementById(id);
// le toast (simple / erreur / avec action RM2451), les références cliquables (RM2585/2596/2718 — un écouteur en capture sur le document)
// et le runner PM partagé : montés d'abord, tous les domaines les empruntent. La fiche ℹ, les fichiers et le glossaire sont lus à l'appel.
const notify = mountNotify(byId("toast"));
const pm = new PmService({ stores });
const links = mountLinks(document, { showTicket: (id) => meta && meta.showTicket(id), openFileRef: (p) => files && files.openRef(p), glossify: (s) => doc.glossify(s), redmineBase: () => CFG.redmine_url || "" });
// la modale doc : documents rendus (RM2309), aide intégrée (RM2593), glossaire du jargon (RM2623) — et les termes
// soulignés partout dans la page. Montée d'abord : tous les panneaux lui empruntent l'aide. Le routeur (center)
// est lu à l'appel, quand un document part au centre.
// la disposition (RM2466/2579/2599/2952) : colonnes repliables, onglets de droite, largeur, préférences. Montée d'abord : les
// domaines la lisent (rightVisible) ; ce qu'un onglet visible déclenche est décidé ici, après que tous sont montés (onApply lit
// les contrôleurs à l'appel, jamais au montage).
const layout = mountLayout({ mnav: byId("mnav"), main: document.querySelector("main"), lnav: document.querySelector(".lnav"), lbody: document.querySelector(".lbody"), rpanel: byId("rpanel"), rnav: document.querySelector("#rpanel .rnav"), rtoggle: byId("rtoggle"), ltoggle: byId("ltoggle"), rhandle: byId("rhandle"), startOpen: byId("rp-startopen"), defTab: byId("rp-deftab") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), root: document,
  // RM3003 : gabarit mobile — écran étroit (media query) ou ?layout=mobile ; la barre du bas compte les sessions qui attendent
  media: (typeof window !== "undefined" && window.matchMedia) ? window.matchMedia("(max-width: " + MOBILE_MAX_PX + "px)") : null, search: (typeof location !== "undefined" ? location.search : ""),
  attention: () => stores.sess.values().filter(s => s && !s.ghost && (s.state === "attention" || s.state === "choice")).length, attached: () => (attachCtl ? attachCtl.current() : null),
  onApply: (r, visible) => {
    const att = attachCtl.current();
    if (visible("outline") && att) outlineCtl.load();                       // RM2330 : ne charge qu'une fois réellement visible
    if (visible("infos") && meta) meta.renderInfos();                       // RM2579 : (re)peuple l'onglet visible
    if (visible("tickets") && meta) meta.renderTickets();
    if (visible("state") && worklogCtl) worklogCtl.load();                  // RM2581
    if (visible("files") && files) files.ensure();                          // RM2586/2673 : compare le contexte, pas le seul sid
    if (visible("git") && att) git.refresh();                               // RM2602
    if (visible("projects") && sessproj) sessproj.refresh();               // RM3045 : compare le sid, recharge si la session a changé
  },
  onResized: () => terminal.fit(),   // le terminal (migré) se réajuste après un redimensionnement
  // RM2283/2760/2816 : les panneaux gauche à contenu serveur chargent à leur première activation (lus à l'appel, jamais au montage)
  panelLoaders: { sessions: () => { resume.load(); setsCtl.load(); }, test: () => testqueue.load(), mail: () => mail.refresh(), projects: () => projects.refresh() },
});
const doc = Object.assign(mountDocModal(byId("docmodal"), { root: document, openCenterFile: (src, wt, p) => center.openFile(src, wt, p) }), { glossaireRows, glossaireFiltre });
const mail = mountMailPanel(document.getElementById("lp-mail"), {
  notify: notify.toast,
  help: (t) => doc.openHelp(t),
  openCenter: (k, sujet) => center.openMail(k, sujet),
  badge: (n) => { const b = document.getElementById("ln-mail"); if (b) { b.textContent = n || ""; b.style.display = n ? "" : "none"; } },
});

const git = mountGitPanel(document.getElementById("rp-git"), {
  notify: notify.toast,
  attached: () => attachCtl.current(),
  branchesOf: (sid) => ((stores.sess.get(sid) || {}).registry || {}).branches || [],
  openCenter: (sid, sha) => center.openCommit(sid, sha),
});

const dashboard = mountDashboard(document.getElementById("dashboard"), {
  notify: notify.toast,
  attach: (rm) => attachCtl.attach(rm), openReview: (rm) => review.open(rm),
  pull: () => refreshCtl.fetch(["dashboard"]),
  sessions: () => stores.sess.view,
  stale: () => [...refreshCtl.stale()],
  nameOf: entryLabel,
  // visible = le vide central est affiché et aucune session n'est attachée (RM2697)
  visible: () => { const ph = document.getElementById("placeholder"); return !!ph && ph.style.display !== "none" && !attachCtl.current(); },
  // RM2744 : dès qu'il y a du contenu, l'alignement passe en haut ; l'indice s'efface
  shown: (on, hasContent) => {
    const box = document.getElementById("dashboard"), hint = document.getElementById("ph-hint"), ph = document.getElementById("placeholder");
    if (box) box.style.display = on ? "" : "none";
    if (ph) ph.classList.toggle("dash-on", on);
    if (hint) hint.style.display = on && hasContent ? "none" : "";
  },
});

const projects = mountProjectsPanel(document.getElementById("lp-projects"), {
  notify: notify.toast, help: (t) => doc.openHelp(t),
  sessions: () => stores.sess.values(),
  resolve: () => stores.resolve,
  clientContext: () => launcher.clientContext(),
  pin: (kind, key) => center.pinOf(kind, key),
  openProject: (key) => project.open(key), openClient: (c) => center.openClient(c), openConf: (scope, c, p) => center.openConf(scope, c, p),
});

// santé du poste et verrous : la modale partagée (docmodal) lui est prêtée, comme
// le badge et le bouton d'en-tête — trois surfaces, un contrôleur.
const env = mountEnv(document.getElementById("doccontent"), {
  notify: notify.toast, clip: (txt) => terminal.writeClip(txt),   // presse-papier avec replis (terminal migré)
  pull: (block) => refreshCtl.fetch([block]),
  secure: () => !!window.isSecureContext,
  modal: (title, cls) => { const t = document.getElementById("doctitle"), c = document.getElementById("doccontent"), m = document.getElementById("docmodal");
    if (t) t.textContent = title; if (c) c.className = cls; if (m) m.classList.add("show"); },
  badge: (h) => { const el = document.getElementById("envwarn"); if (el) { paint(el, h); el.style.display = String(h || "") ? "" : "none"; } },
  lock: (s) => { const el = document.getElementById("lockbtn"); if (el) { el.style.display = s.show ? "" : "none"; el.textContent = s.label; el.title = s.title; } },
});

const pmcmd = mountPmCommands(document.getElementById("pmcard"), {
  notify: notify.toast, help: (t) => doc.openHelp(t), run: (n, a, o) => pm.run(n, a, o),
});
const memory = mountMemory({ card: byId("memorycard"), settings: byId("probecard") }, {
  probe, storage: localStorage, notify: notify.toast, help: (t) => doc.openHelp(t),
  download: (name, text) => { const a = document.createElement("a"); const url = URL.createObjectURL(new Blob([text], { type: "application/json" })); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); },
});
const settings = mountSettings(document.getElementById("reglages-card"), document.getElementById("themecard"), {
  // RM3063 : filtre « Clients » masqué par défaut — appelé au montage, AVANT la déclaration de `show` (TDZ) : DOM direct
  applyClientCtx: (on) => { const el = document.getElementById("clientctx"); if (el) el.style.display = on ? "inline-block" : "none"; },
  notify: notify.toast, help: (t) => doc.openHelp(t), applyTheme: () => { if (typeof window.applyTheme === "function") window.applyTheme(); },
  effectiveTheme: () => document.documentElement.getAttribute("data-theme"),
});

// la voix : les moteurs du navigateur sont fournis ICI, au seul endroit qui les connaît
const synth = () => (typeof speechSynthesis !== "undefined" ? speechSynthesis : null);
const voice = mountVoice(document.getElementById("voicecard"), {
  notify: notify.toast, storage: localStorage,
  attached: () => attachCtl.current(), resolve: () => stores.resolve,
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
const show = (id, on, mode = "block") => { const el = byId(id); if (el) el.style.display = on ? mode : "none"; };
let journal = null, cdc = null, clientnotify = null, sessproj = null, project = null, review = null, testqueueRef = null, meta = null, tickets = null, files = null, worklogCtl = null, launcher = null, terminal = null, sessionsCtl = null, setsCtl = null, refreshCtl = null;
const centerCore = mountCenter({ tabs: byId("ctabs"), hist: byId("histbox"), view: byId("viewpane"), title: byId("curtitle") }, {
  storage: localStorage, notify: notify.toast, notifyAction: notify.toastAction, md: mdToHtml,
  resolve: () => stores.resolve,
  scope: () => ({ filesData: files.data(), attached: attachCtl.current(), projectKey: project ? project.current() : null }),
  surfaces: {
    session:   { sessions: () => stores.sess.view, list: async () => (await get(route("session.sessions")) || {}).sessions || [],
                 open: (rm) => attachCtl.attach(rm), relaunch: (s) => setsCtl.relaunchGhost(s), close: () => { if (attachCtl.current()) () => attachCtl.detach()(); } },
  },
  panels: {
    pm:       { label: "commandes pm", load: () => pmcmd.load(),    show: (on) => show("cp-pm", on) },
    settings: { label: "réglages",     load: () => settings.load(), show: (on) => show("cp-settings", on) },
    journal:  { label: "journal",      load: () => journal.load(true), show: (on) => { show("cp-journal", on); journal.setVisible(on); } },   // RM3011
    memory:   { label: "mémoire",      load: () => memory.render(),   show: (on) => { show("cp-memory", on); memory.setVisible(on); } },     // RM3007
    cdc:      { label: "CDC",          load: () => cdc.open(),          show: (on) => show("cp-cdc", on) },                      // RM3044 : un menu, trois onglets dedans
    clientnotify: { label: "compte-rendu", load: () => clientnotify.open(), show: (on) => show("cp-clientnotify", on) },                 // RM3052 : ce qui est livré et pas encore annoncé
  },
  panelShow: (on) => show("panelpane", on), viewShow: (on) => show("viewpane", on),
  noted: () => layout.centerShown(),   // RM3003 : une vue, une session, un panneau ou une fiche ouverte → la page « centre » du gabarit mobile
  placeholder: (on) => show("placeholder", on, "flex"),
  dashboard: () => dashboard.refresh(),
  nothingElse: () => !attachCtl.current() && !(review && review.current()) && !(project && project.current()),
  histOpen: () => { const b = byId("histbox"); return !!b && b.style.display !== "none"; },
  histShow: (on) => show("histbox", on),
  navButtons: ({ back, fwd }) => { const b = byId("histback"), f = byId("histfwd"); if (b) b.disabled = !back; if (f) f.disabled = !fwd; },
  legacyTitle: () => (sessionsCtl ? sessionsCtl.titleHtml() : "") || (review && review.current() ? review.titleHtml((rm, tt) => links.titleLink(rm, tt)) : "") || (project ? project.titleHtml() : ""),
  afterTitle: () => { if (sessionsCtl) sessionsCtl.afterTitle(); },   // RM2894/2302/2327 : en-tête droit, « ✔ Oui », auto-oui suivent la vue
  // RM2795 : les listes portent la même marque d'épinglage — elles se redessinent au geste
  onPinChange: () => { tickets.renderOpened(); projects.render(); if (worklogCtl && worklogCtl.data().found) worklogCtl.render(); try { refreshCtl.refreshSessions(); } catch (e) {} },
});
const center = Object.assign(centerCore, {
  scopeTagOf: (wt) => scopeTag(fsScope(wt, files.data(), attachCtl.current(), project ? project.current() : null)),
  fileBodyHtml: (f) => String(FileBody(new FileViewModel(f, { md: mdToHtml }))),
  centerBtn: centerBtnHtml,
});
// première surface migrée : elle remplace son pont. RM2726 : la cible par défaut
// est celle du lanceur éclair (#nt-project), elle-même posée par le contexte client.
const newticket = mountNewTicket(byId("ntpane"), {
  center, notify: notify.toast, openReview: (rm) => review.open(rm),
  show: (on) => show("ntpane", on),
  config: () => ({ types: (CFG).task_types || [], priorities: (CFG).priorities || [] }),
  projects: () => launcher.projects(),
  defaultTarget: () => { const cur = ((byId("nt-project") || {}).value || "").split("/"); return { client: cur[0] || launcher.clientContext(), project: cur[1] || "" }; },
});
center.register("newticket", { open: newticket.open, close: newticket.close });
// la fiche projet : deuxième surface enregistrée
project = mountProject(byId("projpane"), {
  center, notify: notify.toast, run: (n, a, o) => pm.run(n, a, o),
  show: (on) => show("projpane", on),
  sessions: (key) => (sessionsCtl ? sessionsCtl.groups() : {})[key] || [],
  attach: (rm) => attachCtl.attach(rm), showTicket: (id) => meta.showTicket(id), openDoc: (p, n) => doc.openDoc(p, n),
  titleLink: (rm, t) => links.titleLink(rm, t), ago: ago,
  mrLine: (m) => String(MrLine(mrLine(m))), mergeMr: (url, iid, target, btn) => worklogCtl && worklogCtl.mergeOne(url, iid, target, btn),   // RM2723 : rendu et geste partagés avec le worklog de session
  fileBody: (f) => center.fileBodyHtml(f),
  filesEnsure: () => { if (layout.rightVisible("files")) files.ensure(); },
});
center.register("project", { open: project.open, close: () => { if (project.current()) project.close(); } });
// le modèle ticket : la logique dans le module, le stockage dans les stores nommés (RM3005) — les vues lisent `get`, ou s'abonnent
const ticketRepo = new TicketRepository({ stores });
const ticket = {
  stale: (rm) => ticketRepo.stale(rm),
  inFlight: (rm) => !!ticketRepo.inflight.resolve[String(rm)],   // RM2807 : garde anti fan-out des listes du monolithe
  ensureResolved: (rm, force) => ticketRepo.ensureResolved(rm, force),
  revalidate: (rm, after) => ticketRepo.revalidate(rm, after),
  /** Rechargement explicite (⟳) : recharge, puis re-rend ce que le monolithe affiche encore. */
  reload: (rm) => ticketRepo.ensureResolved(String(rm), true).then(() => {
    rm = String(rm);
    if (meta && meta.ticketIs(rm)) meta.render();
    if (review && review.current() === rm) review.render();
    if (launcher && launcher.rm() === rm) launcher.resolve();
    notify.toast("RM" + rm + " rechargé");
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
  attached: () => attachCtl.current(), notify: notify.toast, linkify: (s) => links.linkify(s), clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
});
// la carte « Reprendre une session » (RM1939/2834/2991/2418) : projets connus, contexte client, lanceur, attache et suites d'une reprise prêtés
const resume = mountResume(byId("rescard"), {
  notify: notify.toast, ago: ago, markPill: (m) => links.markPillHtml(m), projects: () => launcher.projects(),
  launcherRm: () => (byId("rm") || {}).value || "", attach: (rm) => attachCtl.attach(rm),
  afterResume: async (r) => { setsCtl.warnSpawn(r); await refreshCtl.refreshSessions(); refreshCtl.refreshHealth(); },
});
// l'onglet 📂 fichiers (RM2586/2622/2659/2673/2675/2759/2861) : le contexte de lecture (session, fiche de ticket, fiche projet,
// jeu courant), le rendu commun d'un fichier, la portée d'un worktree et l'ouverture au centre sont prêtés
files = mountFiles({ body: byId("filesbody"), count: byId("filescnt"), nav: document.querySelector("#rp-files .outnav") }, {
  notify: notify.toast, attached: () => attachCtl.current(), resolve: () => stores.resolve,
  reviewCurrent: () => (review ? review.current() : null), projectKey: () => (project ? project.current() : null),
  sets: () => setsCtl.sets(), currentSet: () => setsCtl.current(),
  fileBody: (f) => String(FileBody(new FileViewModel(f, { md: mdToHtml }))), scopeTagOf: (wt) => center.scopeTagOf(wt), showRight: layout.showRight,
  center: { openFile: (src, wt, p, tag) => center.openFile(src, wt, p, tag), openDir: (src, wt, p, tag) => center.openDir(src, wt, p, tag), openCommit: (sid, hash) => center.openCommit(sid, hash) },
});
// le panneau 🎫 tickets (RM1952 triage, RM2606 tickets ouverts, RM2619 infobulles) : le monolithe prête les résolutions,
// la fiche ℹ (meta), l'épinglage, le contexte client et le chemin partagé de lancement d'un lot (RM2823/2831)
tickets = mountTicketsPanel({ triage: byId("triagecard"), opened: byId("openedcard"), badge: byId("ln-tickets") }, {
  ticket, notify: notify.toast, storage: (typeof localStorage !== "undefined" ? localStorage : null), root: document,
  resolve: () => stores.resolve, showTicket: (id) => meta && meta.showTicket(id), pinOf: (k, key) => center.pinOf(k, key),
  clientContext: () => launcher.clientContext(), spawnBatch: (items, btn, opts) => worklogCtl.spawnBatch(items, btn, opts),
});
// la recherche de tickets (RM2770/2639/2830) : projets connus, contexte client, statuts NORMS, lien de titre, épinglage prêtés ;
// un résultat cliqué prépare le lanceur, une étiquette chargée alimente aussi le menu du triage
const search = mountSearch(byId("searchcard"), {
  notify: notify.toast, projects: () => launcher.projects(), clientContext: () => launcher.clientContext(),
  statuses: () => ((CFG).statuses) || [], redmineBase: () => ((CFG).redmine_url) || "",
  titleLink: (rm, tt) => links.titleLink(rm, tt), pinOf: (k, key) => center.pinOf(k, key),
  pick: (rm) => launcher.setRm(rm, { switchPanel: true, scroll: true }),   // RM2283 : le lanceur vit dans « sessions »
  openExternal: (url) => window.open(url, "_blank", "noopener"), onTags: (tags) => tickets.setTags(tags),
});
// l'onglet 🗒 worklog et ses lots (RM2466/2581/2716/2720/2723/2786/2823/2831) : la session attachée, le registre, CFG, le runner PM,
// la capture, la modale doc (écrans de lot), l'infobulle, la marque, linkify, la revue, la fiche ℹ, le lanceur et l'attache sont prêtés
worklogCtl = mountWorklog({ body: byId("workbody"), fresh: byId("workfresh"), nav: document.querySelector("#rp-state .outnav") }, {
  ticket, notify: notify.toast, ago: ago, run: (n, a, o) => pm.run(n, a, o), capture: (t, txt) => doc.openPlain(t, txt),
  attached: () => attachCtl.current(), sess: () => stores.sess, cfg: () => CFG, resolve: () => stores.resolve,
  tipAttr: (id) => tickets.tipAttr(id), pinOf: (k, key) => center.pinOf(k, key), linkify: (s) => links.linkify(s),
  openReview: (rm) => review.open(rm), openStatusMenu: (ref, n, e) => review.openStatusMenu(ref, n, e), showTicket: (rm) => meta && meta.showTicket(rm),
  modal: { open: (t, f, on) => doc.openCustom(t, f, on), close: () => doc.closeDoc(), content: () => doc.contentEl() },
  launcher: () => ({ engine: (byId("engine") || {}).value || "claude", model: (byId("model") || {}).value || "" }),
  warnSpawn: (r) => setsCtl.warnSpawn(r), refreshSessions: (() => refreshCtl.refreshSessions()), attach: (rm) => attachCtl.attach(rm), forgetOpened: (rm) => tickets.forget(rm),
  forgetTicketSessions: (rm) => ticketRepo.forgetTicketSessions(rm),
  openExternal: (u) => window.open(u, "_blank", "noopener"), projectWorklog: () => project && project.refreshWorklog(),
  afterLoad: () => { if (layout.rightVisible("tickets") && meta) meta.renderTickets(); },   // RM2673 : le worklog alimente la liste des tickets
});
// les actions d'une session (RM1893 §2 chips, RM2720 actions PM d'un ticket, §3 moniteurs, RM2515 disposition, fermeture) :
// la session attachée, le registre, CFG, le détachement et les rafraîchissements sont prêtés
const actions = mountSessionActions({ chips: byId("chipsrow"), bar: byId("tabactions") }, {
  notify: notify.toast, attached: () => attachCtl.current(), sess: () => stores.sess, cfg: () => CFG,
  detach: () => attachCtl.detach(), refreshSessions: (() => refreshCtl.refreshSessions()), refreshHealth: (() => refreshCtl.refreshHealth()),
  popover: () => { const m = document.createElement("div"); m.className = "dispmenu"; m.id = "dispmenu"; document.body.appendChild(m); return m; },
  place: (m, anchor) => { const r = anchor.getBoundingClientRect(); m.style.left = Math.round(Math.min(r.left, window.innerWidth - m.offsetWidth - 6)) + "px"; m.style.top = Math.round(r.bottom + 4) + "px"; },
  onOutsideClick: (fn) => setTimeout(() => document.addEventListener("click", fn, { once: true }), 0),
});
// le terminal de la session attachée (RM2522 client maison opt-in / iframe ttyd, RM2700 cookie de gate, RM2807 sonde) et le composer
// (RM2527 garde d'état, historique de ce navigateur), copies RM2168/2631 : CFG, le token, l'état live des sessions et la modale texte sont prêtés
terminal = mountTerminal({ host: byId("termhost"), frame: byId("term"), composer: byId("composer") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), win: window, cfg: () => CFG, notify: notify.toast,
  attached: () => attachCtl.current(), sess: () => stores.sess, token: () => auth.token(),
  setCookie: (c) => { document.cookie = c; }, clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
  copyFallback: (txt) => { const ta = document.createElement("textarea"); ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.focus(); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; } ta.remove(); return ok; },
  capture: (t, txt) => doc.openPlain(t, txt), domCount: () => document.getElementsByTagName("*").length,
});
// la revue : troisième surface enregistrée. Le monolithe lui prête l'encart ℹ, les sessions,
// l'attache, le lanceur (moteur/modèle), la recherche par étiquette, les actions PM.
review = mountReview(byId("reviewpane"), {
  center, ticket, run: (n, a, o) => pm.run(n, a, o), notify: notify.toast, capture: (t, txt) => doc.openPlain(t, txt), md: mdToHtml,
  titleLink: (rm, tt) => links.titleLink(rm, tt), eff: effDisposition,
  resolve: () => stores.resolve, cfg: () => CFG,
  show: (on) => show("reviewpane", on),
  setMeta: (rm) => meta && meta.setTicket(rm), metaIs: (rm) => !!(meta && meta.ticketIs(rm)), renderMeta: () => meta && meta.render(),
  noteOpened: (rm) => tickets.noteOpened(rm), showRight: layout.showRight, refreshSessions: (() => refreshCtl.refreshSessions()),
  filesEnsure: () => { if (layout.rightVisible("files")) files.ensure(); },
  afterStatus: (rm) => { if (launcher && launcher.rm() === String(rm)) launcher.resolve(); if (attachCtl.current() && layout.rightVisible("state")) worklogCtl.load(true); },
  attach: (rm) => attachCtl.attach(rm), warnSpawn: (r) => setsCtl.warnSpawn(r), filterByTag: (tag) => { layout.switchPanel("tickets"); search.setTag(tag); },
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
Object.assign(review, { taskPromptText, promptFillOnChange, promptTemplateOptions: (sel) => html`${promptTemplates().map(t => html`<option ${attrs({ value: t.value, selected: t.value === String(sel == null ? "" : sel) })}>${t.label}</option>`)}` });
center.register("review", { open: review.open, close: () => { if (review.current()) review.close(); } });
// le lanceur (§1 résolution, RM1941 modèles, RM2873 consigne, RM2818 garde, spawn), la saisie éclair d'un ticket (§8) et le contexte
// client (RM2639) : CFG, la consigne et la garde (revue), le runner PM, l'attache et les suites sont prêtés ; le contexte prévient le reste
launcher = mountLauncher({ card: byId("launchcard"), ntcard: byId("ntcard"), clientctx: byId("clientctx") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), cfg: () => CFG, notify: notify.toast, capture: (t, txt) => doc.openPlain(t, txt), run: (n, a, o) => pm.run(n, a, o),
  promptText: taskPromptText, promptFill: promptFillOnChange, confirmSecondSession: (rm) => review.confirmSecondSession(rm), warnSpawn: (r) => setsCtl.warnSpawn(r),
  afterSpawn: async () => { await refreshCtl.refreshSessions(); refreshCtl.refreshHealth(); }, attach: (rm) => attachCtl.attach(rm), switchPanel: (n) => layout.switchPanel(n),
  afterStatus: async (rm) => { await ticket.ensureResolved(rm, true); if (meta && meta.ticketIs(rm)) meta.render(); if (review.current() === rm) review.render(); },   // RM2229 : re-résout partout
  afterCreate: () => search.refreshIfQuery(),
  onProjects: () => { resume.setProjects(); search.loadTags(); search.init(); },                    // RM2834/2830/2770
  onContext: (c, proj, initial) => { tickets.filterClient(c || null); resume.applyClientContext(c, proj);   // RM2639 : le reste du cockpit suit
    if (!initial) { search.refreshIfQuery(); projects.render(); search.fillProjects(); refreshCtl.refreshSessions(); } },
});
// RM2873 : le lanceur de gauche propose les mêmes modèles de consigne que la fiche
{ const sel = byId("ptpl"); if (sel) paint(sel, review.promptTemplateOptions("traiter")); }
// l'encart ℹ (RM2173/2579/2605/2614/2673/2797) : colonne de droite « infos » + « tickets ». Le monolithe
// lui prête la session attachée, le registre, les stores ticket, le worklog, la colonne et les gestes voisins.
meta = mountMeta({ infos: byId("infosbody"), tickets: byId("ticketsbody") }, {
  ticket, notify: notify.toast, md: mdToHtml, ago: ago, tipAttr: (id) => tickets.tipAttr(id),
  resolve: () => stores.resolve, sess: () => stores.sess, usage: () => stores.usage,
  attached: () => attachCtl.current(), worklog: () => worklogCtl.data(), worklogPending: () => worklogCtl.pending(), loadWorklog: () => worklogCtl.load(),
  showRight: layout.showRight, noteOpened: (id) => tickets.noteOpened(id), gotoTicket: (rm) => launcher.goto(rm), reopen: (rm) => launcher.reopen(rm),
  openReview: (rm) => review.open(rm), reload: (rm) => ticket.reload(rm), openStatusMenu: (rm, anchor, ev) => review.openStatusMenu(rm, anchor, ev), openProject: (key) => project.open(key),
  clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null,
});
// la file « à tester » : panneau de gauche autonome ; la revue lit ses entrées et lui emprunte ses gestes d'env
const testqueue = testqueueRef = mountTestQueue(byId("tqcard"), {
  notify: notify.toast, help: (t) => doc.openHelp(t), run: (n, a, o) => pm.run(n, a, o), capture: (t, txt) => doc.openPlain(t, txt),
  resolveRefresh: (rm) => ticket.ensureResolved(String(rm), true),
  openReview: (rm) => review.open(rm), verdict: (rm, k, b) => review.verdict(rm, k, b), pin: (k, key) => center.pinOf(k, key),
  afterLoad: () => { if (review.current()) review.render(); },
});
// la liste « en cours » (RM2283/2346/2427/2445/2448/2515/2598/2639/2787/2793/2210) et les raccourcis Oui / auto-oui (RM2302/2327/2332),
// le titre de la session attachée et l'en-tête droit (RM2894) : le registre live est PARTAGÉ par référence (sessCache) ; le monolithe prête
// l'attache, les questions sans réponse, la sélection et les jeux (état, setWritable/setLabel, ⊖ ⟳ relance), titleLink et la pile /refresh
sessionsCtl = mountSessions({ list: byId("runlist"), counters: byId("hcnt"), navCount: byId("ln-count"), navAtt: byId("ln-att"), yesAll: byId("yesall"), yesAtt: byId("yesatt"), yesBtn: byId("yesbtn"), autoYes: byId("autoyes"), title: byId("curtitle"), rtitle: byId("rtitle"), dynsort: byId("dynsort") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: notify.toast, ticket,
  sess: () => stores.sess, resolve: () => stores.resolve, attached: () => attachCtl.current(), stale: () => refreshCtl.stale(),
  selection: () => setsCtl.selection(), sets: () => ({ sets: setsCtl.sets(), current: setsCtl.current(), view: setsCtl.view() }),
  writable: (sets, name, view) => setsCtl.writable(sets, name, view), setLabel: (name) => setsCtl.label(name),
  clientContext: () => launcher.clientContext(), setClientContext: (c) => launcher.setClientContext(c),
  pin: (k, key) => center.pinOf(k, key), titleLink: (rm, tt) => links.titleLink(rm, tt),
  composerRefresh: () => terminal.composerRefresh(), attach: (rm) => attachCtl.attach(rm), detach: () => attachCtl.detach(), refresh: (() => refreshCtl.refreshSessions()),
  kill: (rm) => actions.kill(rm), openDispositionMenu: (s, anchor) => actions.openDispositionMenu(s, anchor),
  drop: (s) => setsCtl.dropFromSet(s), relaunch: (s) => setsCtl.relaunchGhost(s), forget: (s) => setsCtl.forgetGhost(s), toggleRestart: (s) => setsCtl.toggleRestart(s),
  openProject: (key) => project.open(key), review: { tabs: () => review.tabs(), current: () => review.current(), open: (rm) => review.open(rm), close: (rm) => review.close(rm) },
  projectsVisible: () => { const p = byId("lp-projects"); return !!p && p.classList.contains("active"); }, renderProjects: () => projects.render(),
  announce: (sessions) => voice.announce(sessions), renderTitle: () => center.title(), docTitle: (t) => { document.title = t; },
});
// les jeux de sessions (RM2395/2442/2445/2446/2448/2449/2451/2452/2673/2741/2955) : barre du panneau « en cours » et carte « Sessions enregistrées » ;
// la liste migrée prête les sessions AFFICHÉES, le monolithe le toast (simple et avec action), confirm/prompt, l'attache et la pile /refresh
setsCtl = mountSets({ bar: byId("setbar"), card: byId("sessions-set-card") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: notify.toast, notifyAction: notify.toastAction,
  confirm: (m) => window.confirm(m), prompt: (m, d) => window.prompt(m, d),
  ordered: () => sessionsCtl.ordered(), refreshSessions: (() => refreshCtl.refreshSessions()), attach: (rm) => attachCtl.attach(rm),
});
// la pile /refresh (RM2763 composite unique, RM2613 cadence adaptative), la pastille de santé, « ⬆ MAJ dispo » (RM2571) et les questions
// sans réponse (RM2598) : les blocs reçus vont aux domaines migrés ; les briefs sèment le store de résolution (RM3005) ; le premier tick
// est déclenché par l'init du monolithe (tickSessions) une fois la configuration connue
refreshCtl = mountRefresh({ health: byId("health"), healthtxt: byId("healthtxt"), updbtn: byId("updbtn"), verwarn: byId("verwarn") }, {
  version: VERSION,   // RM3000 : la version servie par /health est comparée à celle du front
  stores, root: document, alert: (t) => window.alert(t),
  attached: () => attachCtl.current(), worklogVisible: () => layout.rightVisible("state"), dashboardVisible: () => dashboard.visible(),
  onSessions: (list) => sessionsCtl.render(list), onWorklog: (d) => worklogCtl.setFromRefresh(d), onDashboard: (d) => dashboard.setBlock(d), onEnv: (k, d) => env.setBlock(k, d),
  token: () => auth.token(),   // RM3006 : le canal de push (EventSource) porte le jeton en query
  onTopics: (topics) => { if (topics.includes("mail")) mail.refresh(); if (topics.includes("sets") && setsCtl) setsCtl.refreshSets(); },   // sujets sans bloc /refresh
  onPush: () => layout.refreshMobileNav(),
});
// l'authentification (RM2334) : écran de login plein-cadre, cadenas, carte de session et appareils, comptes (superadmin). L'init du monolithe
// appelle `boot` une fois CFG connu ; une connexion relance la santé et les sessions et ramène au panneau « en cours »
auth = mountAuth({ gate: byId("authgate"), card: byId("authcard"), users: byId("userscard"), lock: byId("lock") }, {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), cfg: () => CFG, notify: notify.toast,
  confirm: (m) => window.confirm(m), prompt: (m) => window.prompt(m), ua: (typeof navigator !== "undefined" ? navigator.userAgent : ""),
  afterAuth: () => { refreshCtl.refreshHealth(); refreshCtl.refreshSessions(); }, switchPanel: (n) => layout.switchPanel(n),
});
// l'attache (RM2759/2816/2353/2672/2466/2173/2330/2602/2673/1893/2283/2697) : la session affichée au centre, et les raccourcis clavier de la
// conversation (RM2330 Alt+↑/↓/Fin, RM2527 Alt+C) — elle orchestre les domaines migrés, aucun ne la connaît
attachCtl = mountAttach({ placeholder: byId("placeholder"), tabactions: byId("tabactions"), reviewpane: byId("reviewpane"), chipsrow: byId("chipsrow"), composer: byId("cmptext"), root: document }, {
  center, review, project, newticket, terminal, layout, meta, outline: outlineCtl, worklog: worklogCtl, git, files, actions, dashboard, refresh: refreshCtl,
});
// les boutons statiques de la page (en-tête, aides des panneaux, barre du terminal) : `data-cmd` → geste
const commands = mountCommands(document, {
  "voice-toggle": () => voice.toggle(), "voice-dictate": () => voice.dictate(), "voice-read": () => voice.readQuestion(),
  "nav": (arg) => center.navGo(Number(arg)), "hist": () => center.histToggle(), "panel": (arg) => center.openPanel(arg),
  "help": (arg) => doc.openHelp(arg || undefined), "glossary": () => doc.openGlossary(), "cdc": () => { center.openPanel("cdc"); cdc.open(); },
  "clientnotify": (arg, el) => clientnotify.openMenu(el), "env-status": () => env.openStatus(), "env-vault": () => env.openVault(),
  "new-ticket": () => newticket.open(), "reattach": () => attachCtl.reattach(),
});
// le panneau « journal » (RM3011) : journal du serveur (GET /api/log/tail, relu par since) + journal du front, filtres persistés, badge d'en-tête
// RM3044 : pages du CDC vivant ; RM3045 : onglet projets de la session (prête ses projets au choix du CDC en contexte)
sessproj = mountSessProj(byId("rp-projects"), {
  attached: () => attachCtl.current(), openDoc: (p, n) => doc.openDoc(p, n), showFiles: () => layout.switchRight("files"),
  openCdc: (key, page) => { cdc.select(key); center.openPanel("cdc"); cdc.open(page); },
});
cdc = mountCdc(byId("cdccard"), {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), md: mdToHtml, notify: notify.toast,
  openPanel: () => center.openPanel("cdc"), showTicket: (rm) => review.open(rm), sessionProjects: () => sessproj.keys(),
});
// RM3052 : compte-rendu client — menu déroulant au bandeau (un client par ligne, avec son reste à annoncer),
// page centrale cochable, aperçu de l'email, envoi. Le badge dit combien d'évolutions livrées attendent d'être annoncées.
clientnotify = mountClientNotify(byId("clientnotifycard"), {
  storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: notify.toast,
  openPanel: () => center.openPanel("clientnotify"),
  badge: (txt) => { const b = byId("ln-clientnotify"); if (b) { b.textContent = txt || ""; b.style.display = txt ? "" : "none"; } },
  popover: () => { const m = document.createElement("div"); m.className = "dispmenu"; m.id = "cnmenu"; document.body.appendChild(m); return m; },
  place: (m, anchor) => { const r = anchor.getBoundingClientRect(); m.style.left = Math.round(Math.max(6, Math.min(r.left, window.innerWidth - m.offsetWidth - 6))) + "px"; m.style.top = Math.round(r.bottom + 4) + "px"; },
  onOutsideClick: (fn) => setTimeout(() => document.addEventListener("click", fn, { once: true }), 0),
  clear: (id) => clearTimeout(id),
});
journal = mountJournal({ card: byId("journalcard"), badge: byId("ln-journal") }, { log, storage: (typeof localStorage !== "undefined" ? localStorage : null), notify: notify.toast, clipboard: (typeof navigator !== "undefined" && navigator.clipboard) || null });
// la disposition d'abord (repli des colonnes, onglet de droite, largeur — RM2466/2579/2599), puis les onglets épinglés — jamais une session
// Un domaine qui trébuche à la restauration ou à l'init ne doit pas emporter les autres : chaque étape est isolée (incident du 2026-09-06 :
// une exception au restaurer des onglets épinglés laissait la page à « chargement… », sans init ni gestes).
const safe = (label, fn) => { try { return fn(); } catch (e) { console.error("cockpit : " + label + " en erreur", e); log.error("front", label + " en erreur", { trace: errorBrief(e) }); return undefined; } };
{ const v = byId("ver"); if (v) v.textContent = "cockpit v" + VERSION; }   // RM3000 : pied de page
safe("disposition", () => layout.restore());
safe("onglets épinglés", () => center.restore());

window.karl = Object.freeze({ ...karl, mail, git, dashboard, projects, env, pmcmd, settings, voice, center, newticket, project, testqueue, ticket, review, meta, tickets, doc, outline: outlineCtl, resume, search, files, worklog: worklogCtl, layout, launcher, actions, terminal, sessions: sessionsCtl, sets: setsCtl, refresh: refreshCtl, auth, notify, links, pm, attach: attachCtl, commands, config: CFG, stores, probe, memory, clientnotify, version: VERSION, log, journal });
window.dispatchEvent(new CustomEvent("karl:ready", { detail: window.karl }));

// ── init : ce que le script inline faisait au chargement, dans le même ordre (L6) ──
(async function init() {
  try { Object.assign(CFG, await get(route("session.cockpit_config"))); } catch (e) { /* défauts : le cockpit reste utilisable */ }
  safe("thème", () => settings.setServerTheme(CFG.ui_theme));                              // RM2386 : réconcilie le thème du premier paint avec le défaut d'instance
  safe("moteurs", () => resume.setEngines(CFG.resume_engines || ["claude"]));               // RM2539 : moteurs réellement reprenables
  safe("auth", () => auth.boot());                                                           // RM2334 : carte, jeton mémorisé, écran de login, whoami
  safe("config", () => { actions.fillPresets(CFG); launcher.populateModels(); launcher.fillTicketForm(); });   // moniteurs/dispositions, modèles (RM1941), types/priorités
  safe("projets", () => launcher.loadProjects());                                            // projets connus → formulaires, reprise, recherche, contexte client
  safe("panneau", () => layout.restorePanel());                                              // RM2283 : dernier panneau gauche actif
  if (CFG.auth_required && !auth.token()) safe("réglages", () => center.openPanel("settings"));   // RM2334/RM2816 : sans jeton, les réglages sont ce qu'on vient chercher
  safe("voix", () => { voice.boot(); try { speechSynthesis.onvoiceschanged = () => voice.paint(); } catch (e) { /* pas de synthèse */ } });   // RM2329/2350/2532
  safe("jeux", () => { setsCtl.refreshSets(); setsCtl.refreshSet(); });                      // RM2442 / RM2395
  safe("tableau de bord", () => dashboard.refresh()); safe("poste", () => env.boot());       // RM2697 / RM2722-2748
  safe("compte-rendu client", () => clientnotify.refresh());                                 // RM3052 : combien d'évolutions livrées attendent d'être annoncées
  refreshCtl.start();                                                                        // pile /refresh : premier tick (tous les blocs dus), cadence adaptative
})();
