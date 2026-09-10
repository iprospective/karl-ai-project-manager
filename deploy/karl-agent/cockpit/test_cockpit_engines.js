#!/usr/bin/env node
// Tests du panneau Moteurs (RM3069) : deux familles, la commande est MONTRÉE avant d'agir, le client
// n'envoie qu'un identifiant, la mise à jour sous sessions vives demande une seconde confirmation.
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

  const data = { catalogue: {
      engines: [{ id: "claude", kind: "engine", label: "Claude Code", bin: "claude", sudo: true, config: "compte Claude", note: "", provider_type: "", install_cmd: "sudo -n npm install -g @anthropic-ai/claude-code", update_cmd: "sudo -n npm update -g @anthropic-ai/claude-code" },
                { id: "opencode", kind: "engine", label: "opencode", bin: "opencode", sudo: true, config: "", note: "", provider_type: "", install_cmd: "sudo -n npm install -g opencode-ai", update_cmd: "sudo -n npm update -g opencode-ai" }],
      servers: [{ id: "ollama", kind: "server", label: "Ollama", bin: "ollama", sudo: true, config: "", note: "sert les modèles", provider_type: "ollama", install_cmd: "sudo -n sh -c curl…", update_cmd: "sudo -n sh -c curl…" }] },
    etats: [{ id: "claude", installed: true, version: "2.1.267", latest: "2.2.0", update_available: true, sessions: ["karl-RM1", "karl-RM2"], service: "" },
            { id: "opencode", installed: false, version: "", latest: "", update_available: false, sessions: [] },
            { id: "ollama", installed: true, version: "0.5.1", latest: "", update_available: false, sessions: [], service: "active" }] };

  const vm = new VM.EnginesViewModel({ data });
  const [gEng, gSrv] = vm.groupes;
  assert.deepStrictEqual(gEng.rows.map(r => r.id), ["claude", "opencode"], "les moteurs de session");
  assert.deepStrictEqual(gSrv.rows.map(r => r.id), ["ollama"], "les serveurs de modèles, à part");
  assert(gSrv.rows[0].providerType === "ollama", "un serveur pointe le type de fournisseur qu'il alimente");
  const cl = gEng.rows[0], oc = gEng.rows[1];
  assert(cl.state === "à mettre à jour" && cl.action === "update" && cl.cmd.includes("npm update"), "installé et en retard : on propose la mise à jour");
  assert(oc.state === "absent" && oc.action === "install" && oc.cmd.includes("npm install"), "absent : on propose l'installation");
  assert(/2 session\(s\) en cours/.test(cl.warn), "l'avertissement dit ce que la mise à jour couperait");
  assert(gSrv.rows[0].state === "à jour" && gSrv.rows[0].service === "active", "un serveur montre l'état de son service");
  assert.strictEqual(vm.count, "2 installé(s) sur 3");
  console.log("✓ ViewModel : deux familles, état, version disponible, sessions, service");

  const s = String(V.EnginesCard(vm, "journal de sortie"));
  assert(!/\son\w+=/.test(s), "aucun on* dans la vue");
  assert(s.includes("sudo -n npm update -g @anthropic-ai/claude-code"), "la commande EXACTE est affichée avant d'agir");
  assert(/data-action="run" data-id="claude" data-act="update"/.test(s) && /data-action="test"/.test(s), "gestes en data-action");
  assert(/journal de sortie/.test(s), "la sortie d'exécution est rendue");
  console.log("✓ vue : commande montrée, gestes en data-*, sortie affichée");

  const el = fakeEl("enginescard"); const envoyes = []; let confirme = true; const demandes = [];
  const svc = { data, load: async () => data, run: async (b) => {
    envoyes.push(b);
    if (b.dry_run) return { ok: true, cmd: "sudo -n npm update -g @anthropic-ai/claude-code", dry_run: true };
    if (b.action === "test") return { ok: true, cmd: "claude --version", out: "2.1.267" };
    if (!b.force) return { ok: false, cmd: "…", blocked: ["karl-RM1"], error: "1 session(s) tournent avec claude" };
    return { ok: true, cmd: "…", out: "mis à jour" };
  } };
  const ctl = mountEngines(el, { service: svc, notify: () => {}, confirm: (m) => { demandes.push(m); return confirme; } });
  await ctl.load();
  await el.click("run", { id: "claude", act: "update" });
  assert(envoyes[0].dry_run === true, "on demande d'abord la commande au serveur, sans l'exécuter");
  assert(demandes[0].includes("sudo -n npm update"), "la confirmation MONTRE la commande");
  assert(demandes[0].includes("touche le système"), "et prévient que c'est le système");
  assert(envoyes.every(b => !("cmd" in b) && !("command" in b)), "le client n'envoie JAMAIS de commande, seulement une recette et une action");
  assert(demandes[1] && demandes[1].includes("Forcer"), "sessions vives : seconde confirmation demandée");
  assert(envoyes[envoyes.length - 1].force === true, "forcé seulement après ce second accord");
  confirme = false; envoyes.length = 0; demandes.length = 0;
  await el.click("run", { id: "opencode", act: "install" });
  assert(envoyes.length === 1 && envoyes[0].dry_run === true, "refus à la confirmation : rien n'est exécuté");
  await el.click("test", { id: "ollama" });
  assert(envoyes[envoyes.length - 1].action === "test", "tester n'exige aucune confirmation");
  console.log("✓ contrôleur : commande montrée puis exécutée sur accord, force sur second accord, refus respecté");

  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/id="enginescard"/.test(html), "le panneau a son hôte dans les réglages");
  console.log("\nLe panneau Moteurs passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
