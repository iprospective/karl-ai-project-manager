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
const mail = mountMailPanel(document.getElementById("lp-mail"), {
  notify: legacy("toast"),
  help: legacy("openHelp"),
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
  pull: () => legacy("refreshFetch")(["dashboard"]),
  sessions: () => lexical(() => sessCache) || {},
  stale: () => lexical(() => [...pendStale]) || [],
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
  notify: legacy("toast"), help: legacy("openHelp"),
  sessions: () => Object.values(lexical(() => sessCache) || {}),
  resolve: () => lexical(() => resolveCache) || {},
  clientContext: () => lexical(() => clientContext) || "",
  pin: (kind, key) => legacy("pinOf")(kind, key) || "",
  openProject: legacy("openProjectView"), openClient: legacy("openCenterClient"), openConf: legacy("openCenterConf"),
});

// santé du poste et verrous : la modale partagée (docmodal) lui est prêtée, comme
// le badge et le bouton d'en-tête — trois surfaces, un contrôleur.
const env = mountEnv(document.getElementById("doccontent"), {
  notify: legacy("toast"), clip: legacy("writeClip"),
  pull: (block) => legacy("refreshFetch")([block]),
  secure: () => !!window.isSecureContext,
  modal: (title, cls) => { const t = document.getElementById("doctitle"), c = document.getElementById("doccontent"), m = document.getElementById("docmodal");
    if (t) t.textContent = title; if (c) c.className = cls; if (m) m.classList.add("show"); },
  badge: (h) => { const el = document.getElementById("envwarn"); if (el) { el.innerHTML = h; el.style.display = h ? "" : "none"; } },
  lock: (s) => { const el = document.getElementById("lockbtn"); if (el) { el.style.display = s.show ? "" : "none"; el.textContent = s.label; el.title = s.title; } },
});

const pmcmd = mountPmCommands(document.getElementById("pmcard"), {
  notify: legacy("toast"), help: legacy("openHelp"), run: legacy("pmRun"),
});
const settings = mountSettings(document.getElementById("reglages-card"), document.getElementById("themecard"), {
  notify: legacy("toast"), help: legacy("openHelp"), applyTheme: legacy("applyTheme"),
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

window.karl = Object.freeze({ ...karl, mail, git, dashboard, projects, env, pmcmd, settings, voice });
window.dispatchEvent(new CustomEvent("karl:ready", { detail: window.karl }));
