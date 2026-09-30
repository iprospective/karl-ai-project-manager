#!/usr/bin/env node
// Tests du panneau Moteurs (RM3069) : deux familles, deux PORTÉES (pour moi / pour tous), la commande est
// MONTRÉE avant d'agir, le client n'envoie qu'un identifiant, une action et une portée ; la mise à jour sous
// sessions vives demande une seconde confirmation.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const self = { id, style: {}, dataset: {}, kids: {},
  get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector(s) { return self.kids[s] || null; }, querySelectorAll() { return []; },
  replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener() {},
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); } };
  return self; }
(async () => {
  const VM = await import(path.join(DIR, "src/modules/engines/EnginesViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/engines/Engines.view.js"));
  const { mountEngines } = await import(path.join(DIR, "src/modules/engines/engines.controller.js"));

  const deux = (nom) => ({ user: { install: `npm install -g ${nom}`, update: `npm update -g ${nom}` },
                           system: { install: `sudo -n npm install -g --prefix /usr/local ${nom}`, update: `sudo -n npm update -g --prefix /usr/local ${nom}` } });
  const data = { catalogue: {
      engines: [{ id: "claude", kind: "engine", label: "Claude Code", bin: "claude", config: "compte Claude", note: "", provider_type: "", scopes: ["user", "system"], cmds: deux("@anthropic-ai/claude-code") },
                { id: "opencode", kind: "engine", label: "opencode", bin: "opencode", config: "", note: "", provider_type: "", scopes: ["user", "system"], cmds: deux("opencode-ai") }],
      servers: [{ id: "ollama", kind: "server", label: "Ollama", bin: "ollama", config: "", note: "sert les modèles", provider_type: "ollama", scopes: ["system"], cmds: { system: { install: "sudo -n sh -c curl…", update: "sudo -n sh -c curl…" } } }] },
    etats: [{ id: "claude", installed: true, path: "/home/mathieu/.local/bin/claude", scope: "user", version: "2.1.267", latest: "2.2.0", update_available: true, sessions: ["karl-RM1", "karl-RM2"], service: "" },
            { id: "opencode", installed: false, path: "", scope: "", version: "", latest: "", update_available: false, sessions: [] },
            { id: "ollama", installed: true, path: "/usr/local/bin/ollama", scope: "system", version: "0.5.1", latest: "", update_available: false, sessions: [], service: "active" }] };

  // RM3097 : présent sur la machine, mais dans le home d'un AUTRE développeur
  const dataAilleurs = { ...data, etats: [{ id: "claude", installed: false, installed_elsewhere: true, owner: "bob",
    path: "/home/bob/.local/bin/claude", scope: "other", version: "", latest: "", update_available: false, sessions: [] },
    ...data.etats.slice(1)] };

  const vm = new VM.EnginesViewModel({ data });
  const [gEng, gSrv] = vm.groupes;
  assert.deepStrictEqual(gEng.rows.map(r => r.id), ["claude", "opencode"], "les moteurs de session");
  assert.deepStrictEqual(gSrv.rows.map(r => r.id), ["ollama"], "les serveurs de modèles, à part");
  assert(gSrv.rows[0].providerType === "ollama", "un serveur pointe le type de fournisseur qu'il alimente");
  const cl = gEng.rows[0], oc = gEng.rows[1];
  assert(/à mettre à jour/.test(cl.state) && /pour moi/.test(cl.state), "installé chez l'utilisateur : la portée est dite, pas devinée");
  assert(cl.path === "/home/mathieu/.local/bin/claude", "on montre OÙ il est installé");
  const maj = cl.actions.find(a => a.act === "update");
  assert(maj && maj.scope === "user" && !maj.sudo && maj.cmd.includes("npm update -g @anthropic"), "on met à jour là où il est, sans privilège");
  const ailleurs = cl.actions.find(a => a.act === "install");
  assert(ailleurs && ailleurs.scope === "system" && ailleurs.sudo, "et on peut, en plus, le poser pour tous");
  assert(oc.state === "absent" && oc.actions.length === 2 && oc.actions.every(a => a.act === "install"), "absent : les deux portées sont offertes");
  assert(oc.actions[0].scope === "user" && !oc.actions[0].sudo, "« pour moi » d'abord, sans sudo");
  assert(/2 session\(s\) en cours/.test(cl.warn), "l'avertissement dit ce que la mise à jour couperait");
  const ol = gSrv.rows[0];
  assert(/à jour/.test(ol.state) && /pour tous/.test(ol.state) && ol.service === "active", "un serveur montre sa portée et l'état de son service");
  assert(ol.actions.length === 0, "à jour et sans autre portée possible : rien à proposer");
  assert.strictEqual(vm.count, "2 installé(s) sur 3");
  // RM3097 : « installé » n'a de sens que pour quelqu'un — un binaire du home d'un autre ne compte pas
  const vmA = new VM.EnginesViewModel({ data: dataAilleurs });
  const clA = vmA.groupes[0].rows[0];
  assert(/installé par bob/.test(clA.state) && /pas pour vous/.test(clA.state), "on nomme celui pour qui c'est installé : " + clA.state);
  assert(clA.elsewhere === true && clA.installed === false, "présent sur la machine, mais pas installé POUR VOUS");
  assert(clA.actions.some(a => a.act === "install" && a.scope === "user"), "…donc on propose de l'installer pour soi");
  assert(/pour un autre utilisateur/.test(vmA.count), "le compteur le dit aussi : " + vmA.count);
  console.log("✓ ViewModel : deux familles, deux portées, installé POUR QUI, où c'est installé, ce qu'on peut y faire");

  const s = String(V.EnginesCard(vm, "journal de sortie"));
  assert(!/\son\w+=/.test(s), "aucun on* dans la vue");
  assert(s.includes("npm update -g @anthropic-ai/claude-code"), "la commande EXACTE est affichée avant d'agir");
  assert(/data-action="run" data-id="claude" data-act="update" data-scope="user"/.test(s), "la portée voyage avec le geste");
  assert(/data-scope="system"/.test(s) && /data-action="test"/.test(s), "les deux portées sont proposées, gestes en data-action");
  assert(s.includes("/home/mathieu/.local/bin/claude"), "le chemin réel est montré");
  assert(/journal de sortie/.test(s), "la sortie d'exécution est rendue");
  console.log("✓ vue : portées et commandes montrées, gestes en data-*, sortie affichée");

  const el = fakeEl("enginescard"); const envoyes = []; let confirme = true; const demandes = [];
  const svc = { data, load: async () => data, run: async (b) => {
    envoyes.push(b);
    if (b.dry_run) return { ok: true, cmd: (b.scope === "system" ? "sudo -n " : "") + "npm update -g @anthropic-ai/claude-code", dry_run: true };
    if (b.action === "test") return { ok: true, cmd: "claude --version", out: "2.1.267" };
    if (!b.force) return { ok: false, cmd: "…", blocked: ["karl-RM1"], error: "1 session(s) tournent avec claude" };
    return { ok: true, cmd: "…", out: "mis à jour" };
  } };
  const ctl = mountEngines(el, { service: svc, notify: () => {}, confirm: (m) => { demandes.push(m); return confirme; } });
  await ctl.load();
  await el.click("run", { id: "claude", act: "update", scope: "user" });
  assert(envoyes[0].dry_run === true, "on demande d'abord la commande au serveur, sans l'exécuter");
  assert(envoyes[0].scope === "user", "la portée choisie part avec la demande");
  assert(demandes[0].includes("npm update"), "la confirmation MONTRE la commande");
  assert(demandes[0].includes("pour vous seul"), "et dit pour qui on installe");
  assert(!demandes[0].includes("touche le système"), "une pose « pour moi » n'invoque pas le système");
  assert(envoyes.every(b => !("cmd" in b) && !("command" in b)), "le client n'envoie JAMAIS de commande, seulement une recette, une action et une portée");
  assert(demandes[1] && demandes[1].includes("Forcer"), "sessions vives : seconde confirmation demandée");
  assert(envoyes[envoyes.length - 1].force === true, "forcé seulement après ce second accord");
  assert(envoyes[envoyes.length - 1].scope === "user", "le forçage garde la portée d'origine");
  envoyes.length = 0; demandes.length = 0;
  await el.click("run", { id: "claude", act: "install", scope: "system" });
  assert(demandes[0].includes("pour tous les utilisateurs de la machine") && demandes[0].includes("touche le système"),
         "installer pour tous se dit, et prévient que c'est le système");
  confirme = false; envoyes.length = 0; demandes.length = 0;
  await el.click("run", { id: "opencode", act: "install", scope: "user" });
  assert(envoyes.length === 1 && envoyes[0].dry_run === true, "refus à la confirmation : rien n'est exécuté");
  await el.click("test", { id: "ollama" });
  assert(envoyes[envoyes.length - 1].action === "test", "tester n'exige aucune confirmation");
  console.log("✓ contrôleur : commande montrée puis exécutée sur accord, force sur second accord, refus respecté");

  // ── RM3139 : le LANCEMENT — cocher depuis le cockpit au lieu d'éditer pm.config.yml ──
  const launch = { engines: [
    { engine: "claude", base_cmd: "claude --strict-mcp-config", spawn_cmd: "claude --strict-mcp-config --session-id <uuid>",
      resume_cmd: "claude --strict-mcp-config --resume <session-id>", extra_args: "",
      options: [{ key: "no_mcp", flag: "--strict-mcp-config", label: "désactiver les connecteurs MCP",
                  why: "8 179 tokens par session", enabled: true, source: "défaut" }], problems: [] },
    { engine: "shell", base_cmd: "bash", spawn_cmd: "bash", resume_cmd: null, extra_args: "--login",
      options: [], problems: ["extra_args : --session-id est posé par PM lui-même — à retirer"] }] };

  const lv = new VM.EngineLaunchViewModel({ data: launch });
  assert.deepStrictEqual(lv.rows.map(r => r.engine), ["claude", "shell"], "un bloc par moteur");
  assert(lv.rows[0].options[0].enabled && lv.rows[0].options[0].why.includes("8 179"),
         "l'option porte son état ET son pourquoi — on ne coche pas ce qu'on ne comprend pas");
  assert.strictEqual(lv.rows[0].cmd, "claude --strict-mcp-config --session-id <uuid>", "la commande réelle est celle du serveur");
  assert.deepStrictEqual(lv.rows[1].problems.length, 1, "les problèmes de configuration remontent");
  assert(/tous aux valeurs par défaut/.test(lv.count) === false && /réglé/.test(lv.count), "compte les moteurs réglés ici (shell a des extra_args)");
  // le brouillon prime sur le serveur : sinon la case se recoche sous les doigts au re-rendu
  const lv2 = new VM.EngineLaunchViewModel({ data: launch, dirty: { claude: { options: { no_mcp: false } } } });
  assert.strictEqual(lv2.rows[0].options[0].enabled, false, "ce qu'on vient de décocher reste décoché");
  assert.strictEqual(lv2.rows[0].dirty, true, "…et le bloc est marqué comme non enregistré");
  const vueL = V.EnginesLaunchCard(lv);
  assert(/type="checkbox"/.test(vueL) && /--strict-mcp-config/.test(vueL) && /options libres/.test(vueL)
         && /pm\.config\.local\.yml/.test(vueL), "la vue : cases, commande, champ libre, et où ça s'écrit");
  assert(!/\son\w+=/.test(vueL), "aucun handler inline dans la vue (RM2889)");
  assert(/options indisponibles/.test(V.EnginesLaunchCard(new VM.EngineLaunchViewModel({ data: { engines: [], error: "boum" } }))),
         "catalogue injoignable : le panneau le dit au lieu de disparaître");
  console.log("✓ lancement : options cochables, pourquoi, commande réelle, brouillon, problèmes (RM3139)");

  // le contrôleur : cocher marque le brouillon, enregistrer envoie l'état COMPLET, un refus se dit
  const envoyesOpt = []; let refuse = false;
  const svcL = { data, launch, async load() {}, async run() { return {}; },
                 async saveOptions(b) { envoyesOpt.push(b); if (refuse) throw new Error("réglage refusé : option inconnue"); return { ok: true }; } };
  const el2 = fakeEl("enginescard");
  const notes = [];
  const c2 = mountEngines(el2, { service: svcL, notify: (m, err) => notes.push([m, !!err]), confirm: () => true });
  c2.render();
  c2.state.dirty = { claude: { options: { no_mcp: false }, extra_args: null } };
  await el2.click("save", { engine: "claude" });
  assert.strictEqual(envoyesOpt.length, 1, "enregistrer envoie une fois");
  assert.deepStrictEqual(envoyesOpt[0], { engine: "claude", options: { no_mcp: false }, extra_args: "" },
                         "l'état COMPLET des cases part au serveur : c'est lui qui compare aux défauts");
  assert(!c2.state.dirty.claude, "enregistré : le brouillon est oublié");
  refuse = true; c2.state.dirty = { claude: { options: { no_mcp: true }, extra_args: null } };
  await el2.click("save", { engine: "claude" });
  assert(notes[notes.length - 1][1] === true && /refusé/.test(notes[notes.length - 1][0]),
         "un réglage refusé par le serveur se DIT — il ne s'écrit pas en silence");
  assert(c2.state.dirty.claude, "…et le brouillon est gardé, pour corriger sans tout retaper");
  console.log("✓ contrôleur du lancement : brouillon, envoi complet, refus dit et gardé");

  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/id="enginescard"/.test(html), "le panneau a son hôte dans les réglages");
  console.log("\nLe panneau Moteurs passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
