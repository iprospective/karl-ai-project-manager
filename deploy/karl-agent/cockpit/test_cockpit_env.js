#!/usr/bin/env node
// Tests du domaine env/vault migré (RM2889, L5) — porte RM2458/2708/2722/2748 de test_cockpit.js.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() {
  const L = []; let inner = ""; const fields = {};
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, fields,
    querySelector(sel) { const id = sel.slice(1); if (!(id in fields)) { const m = new RegExp(`id="${id}"[^>]*value="([^"]*)"`).exec(inner); if (m) fields[id] = { value: m[1] }; else if (new RegExp(`id="${id}"`).test(inner)) fields[id] = { value: "" }; } return fields[id] || null; },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; },
    async click(action, extra) { const n = { dataset: { action, ...(extra || {}) }, previousElementSibling: extra && extra.code ? { textContent: extra.code } : null, disabled: false, textContent: "" }; for (const [t, f] of [...L]) if (t === "click") await f({ target: { closest: s => s === "[data-action]" ? n : null } }); return n; },
    async enter(which, btn) { const n = { dataset: { enter: which }, nextElementSibling: btn }; for (const [t, f] of [...L]) if (t === "keydown") await f({ key: "Enter", target: { closest: s => s === "input[data-enter]" ? n : null } }); } };
}
(async () => {
  const M = await import(path.join(DIR, "src/modules/env/envStatus.js"));
  const { EnvBadgeViewModel, EnvStatusViewModel, VaultViewModel } = await import(path.join(DIR, "src/modules/env/EnvViewModels.js"));
  const { EnvBadge, EnvStatus, VaultForm } = await import(path.join(DIR, "src/modules/env/Env.view.js"));
  const { mountEnv } = await import(path.join(DIR, "src/modules/env/env.controller.js"));
  const status = (rep, active) => String(EnvStatus(new EnvStatusViewModel(rep, { active })));
  const badge = (d) => String(EnvBadge(new EnvBadgeViewModel(d || {})));
  const vault = (st, secure) => String(VaultForm(new VaultViewModel(st, { secure })));

  // — RM2458 —
  assert(/état indisponible/.test(status(null)), "rapport absent → message, pas de crash");
  const rep = { generated_at: "2026-08-12T20:00:00", summary: { counts: { ok: 3, info: 0, warn: 1, error: 1 } }, groups: [
    { name: "Outils & dépendances", checks: [{ label: "bw", level: "error", detail: "binaire introuvable", fix: "npm i -g @bitwarden/cli" }, { label: "git", level: "ok", detail: "git version 2.43.0" }] },
    { name: "Git / GitLab", checks: [{ label: "repo pisceen/infra-core [main]", level: "error", detail: "9 non poussés, 3 en retard", fix: "cd /w && git pull --rebase --autostash" }] } ] };
  const esh = status(rep, "Outils & dépendances") + status(rep, "Git / GitLab");
  assert(/es-row es-error/.test(esh) && /es-row es-ok/.test(esh)); assert(/binaire introuvable/.test(esh) && /es-fix">npm i -g @bitwarden\/cli/.test(esh));
  assert(/data-action="copy"/.test(esh) && !/onclick=/.test(esh), "copier sans argument ni onclick");
  assert(esh.indexOf('<code class="es-fix">') < esh.indexOf('data-action="copy"'), "la commande vit dans le <code> AVANT le bouton");
  assert(/es-when">2026-08-12T20:00:00/.test(esh));
  const xss = status({ groups: [{ name: "X", checks: [{ label: "a<b>", level: "warn", detail: "<script>", fix: "x&y" }] }] });
  assert(/a&lt;b&gt;/.test(xss) && !/<script>/.test(xss) && /x&amp;y/.test(xss));
  console.log("✓ santé du poste (RM2458) : niveaux colorés, remédiation copiable, échappement");
  // — RM2708 —
  const G6 = [{ name: "Outils & dépendances", checks: [{ label: "git", level: "ok" }] }, { name: "Git / GitLab", checks: [{ label: "PAT", level: "warn" }, { label: "push", level: "ok" }] },
    { name: "Repos", checks: [{ label: "repo calicote/presta [main]", level: "ok", section: "calicote" }, { label: "repo calicote/dolibarr [dev]", level: "ok", section: "calicote" }, { label: "repo pisceen/presta [main]", level: "error", detail: "9 non poussés", section: "pisceen" }, { label: "repo perso/maths [main]", level: "warn", section: "perso" }, { label: "repos PM", level: "info", detail: "liste tronquée à 120 repos" }] }];
  const tabs = M.envStatusTabs(G6);
  assert.deepStrictEqual(tabs.map(t => t.name), ["Outils & dépendances", "Git / GitLab", "Repos"]); assert.deepStrictEqual({ ...tabs[2] }, { name: "Repos", warn: 1, error: 1, n: 5 });
  assert.strictEqual(M.envStatusDefaultTab(tabs), "Repos"); assert.strictEqual(M.envStatusDefaultTab([{ name: "A", warn: 2, error: 0 }, { name: "B", warn: 0, error: 0 }]), "A");
  assert.strictEqual(M.envStatusDefaultTab([{ name: "A" }, { name: "B" }]), "A"); assert.strictEqual(M.envStatusDefaultTab([]), "");
  assert.deepStrictEqual(M.envStatusSections(G6[2].checks).map(s => s.name), ["", "pisceen", "perso", "calicote"]); assert.strictEqual(M.envStatusSections(G6[2].checks)[3].checks.length, 2); assert.strictEqual(M.envStatusSections([]).length, 0);
  const rep2 = { summary: { counts: {} }, groups: G6 }; const hRepos = status(rep2, "Repos");
  assert(/<details class="es-sec" open><summary>pisceen/.test(hRepos)); assert(/<details class="es-sec"><summary>calicote/.test(hRepos));
  assert(/liste tronquée à 120 repos/.test(hRepos) && !/<summary><\/summary>/.test(hRepos)); assert(!/repo calicote\/presta/.test(status(rep2, "Git / GitLab")));
  assert(/es-badge es-error">✗ 1/.test(hRepos) && /es-badge es-warn">! 1/.test(hRepos)); assert(/data-action="tab" data-tab="Repos"/.test(hRepos)); assert(!/es-sec/.test(status(rep2, "Outils & dépendances")));
  assert.strictEqual(new EnvStatusViewModel(rep2, { active: "disparu" }).current, "Repos", "onglet disparu → défaut");
  console.log("✓ santé du poste (RM2708) : onglets par famille, dépôts sectionnés par client");
  // — RM2722 —
  assert.strictEqual(badge({ items: [], count: 0, worst: "ok" }), ""); assert.strictEqual(badge(null), "");
  const ewWarn = badge({ worst: "warn", items: [{ family: "SSH", label: "agent SSH", level: "warn", detail: "agent joignable mais VIDE" }] });
  assert(/>🩺 1</.test(ewWarn) && /pill ew-warn/.test(ewWarn) && /agent joignable mais VIDE/.test(ewWarn));
  const ewErr = badge({ worst: "error", items: [{ family: "Secrets", label: "vault-agentd", level: "error", detail: "socket absent" }, { family: "SSH", label: "agent SSH", level: "warn", detail: "vide" }] });
  assert(/pill ew-error/.test(ewErr) && />🩺 2</.test(ewErr));
  const ewMany = badge({ worst: "warn", items: Array.from({ length: 12 }, (_, i) => ({ family: "Outils & dépendances", label: "outil" + i, level: "warn", detail: "absent" })) });
  assert(/>🩺 12</.test(ewMany) && /et 4 autre\(s\)/.test(ewMany));
  assert(!/<img/.test(badge({ worst: "warn", items: [{ family: "SSH", label: '"><img src=x>', level: "warn", detail: "x" }] })));
  console.log("✓ badge d'anomalies (RM2722) : silencieux si sain, compté, expliqué au survol");
  // — RM2748 —
  assert.equal(M.vaultBtnState(null).show, false); assert.equal(M.vaultBtnState({ daemon: true, locked: [], ssh: { keys: [{ comment: "k" }] } }).show, false);
  const one = M.vaultBtnState({ daemon: true, locked: ["vw-ipro"], ssh: { keys: [{ comment: "k" }] } }); assert(one.show && /vw-ipro/.test(one.title) && !/agent SSH/.test(one.title));
  const both = M.vaultBtnState({ daemon: false, locked: ["a", "b"], ssh: { keys: [] } }); assert(/coffre fermé/.test(both.title) && /agent SSH vide/.test(both.title));
  assert(/2 coffres/.test(M.vaultBtnState({ daemon: true, locked: ["a", "b"], ssh: { keys: [{}] } }).title));
  const ins = vault({ daemon: true, locked: ["vw-ipro"], ssh: {} }, false); assert(!/type="password"/.test(ins) && /https/.test(ins), "jamais de saisie de secret hors contexte sécurisé");
  const form = vault({ daemon: true, default_instance: "vw-ipro", locked: ["vw-ipro"], instances: [{ slug: "vw-ipro", unlocked: false }, { slug: "kp-client", unlocked: true, since: "2026-08-20T10:00" }], ssh: { reachable: true, keys: [], candidates: ["id_rsa_root", "id_ed25519_gitlab"] } }, true);
  assert(/id="vlt-pass"/.test(form) && /type="password"/.test(form) && /data-action="unlock"/.test(form) && /id="vlt-inst"/.test(form));
  assert(/kp-client/.test(form) && /2026-08-20T10:00/.test(form) && /id="vlt-key"/.test(form) && /id_rsa_root/.test(form) && /data-action="sshadd"/.test(form));
  assert(!/value="[^"]*mot de passe/.test(form) && !/onclick=|onkeydown=/.test(form), "aucun secret pré-rempli, aucun handler inline");
  const open = vault({ daemon: true, locked: [], instances: [{ slug: "vw-ipro", unlocked: true }], ssh: { reachable: true, keys: [{ comment: "root@web-12", type: "RSA", bits: "4096" }], candidates: [] } }, true);
  assert(!/type="password"/.test(open) && /root@web-12/.test(open));
  console.log("✓ verrous (RM2748) : bouton conditionnel, formulaire sûr, rien redemandé quand tout est ouvert");
  // — contrôleur —
  const el = fakeElement(); const ev = []; const sent = [];
  const svc = { check: null, status: null, vault: null,
    setBlock(k, d) { if (k === "envcheck") this.check = d; else this.vault = d; return this; },
    async reloadCheck() { ev.push("reloadCheck"); this.check = { worst: "warn", items: [{ family: "SSH", label: "agent", detail: "vide" }] }; },
    async loadStatus(force) { ev.push(["loadStatus", !!force]); this.status = rep2; },
    async unlock(i, p) { sent.push(["unlock", i, p]); return { ok: true, message: "Coffre déverrouillé" }; },
    async sshAdd(k, p) { sent.push(["sshAdd", k, p]); return { ok: false, message: "Échec : passphrase refusée" }; } };
  const h = mountEnv(el, { service: svc, notify: (m, e) => ev.push(["toast", m, !!e]), clip: async (t) => { ev.push(["clip", t]); return true; }, pull: (b) => { ev.push(["pull", b]); if (b === "vault") svc.vault = { daemon: true, locked: ["vw-ipro"], instances: [], ssh: { reachable: true, keys: [], candidates: ["k1"] } }; },
    secure: () => true, modal: (t, c) => ev.push(["modal", t, c]), badge: (x) => ev.push(["badge", x]), lock: (s) => ev.push(["lock", s.show]) });
  h.boot(); assert.deepStrictEqual(ev.splice(0), [["pull", "envcheck"], ["pull", "vault"]], "au démarrage : deux blocs demandés à la pile /refresh");
  h.setBlock("envcheck", { worst: "warn", items: [{ family: "SSH", label: "a", detail: "d" }] }); assert(/🩺 1/.test(ev.pop()[1]), "bloc envcheck → badge");
  h.setBlock("vault", { daemon: true, locked: ["x"], ssh: { keys: [] } }); assert.deepStrictEqual(ev.pop(), ["lock", true], "bloc vault → bouton");
  await h.openStatus(); assert.deepStrictEqual(ev.shift(), ["modal", "🩺 Santé du poste", ""]); assert.deepStrictEqual(ev.shift(), ["loadStatus", false]); assert(/data-tab="Repos"/.test(el.innerHTML) && /pisceen/.test(el.innerHTML), "page rendue sur la famille en erreur");
  await el.click("tab", { tab: "Git / GitLab" }); assert.strictEqual(h.state.tab, "Git / GitLab"); assert(/PAT/.test(el.innerHTML) && !/pisceen/.test(el.innerHTML), "un onglet ne montre que sa famille");
  await el.click("copy", { code: "npm i -g x" }); assert(ev.some(x => x[0] === "clip" && x[1] === "npm i -g x")); assert(ev.some(x => x[0] === "toast" && x[1] === "Commande copiée"));
  ev.length = 0; await h.openVault(); assert.deepStrictEqual(ev[0], ["modal", "🔓 Verrous du poste", "vlt"]); assert(/id="vlt-pass"/.test(el.innerHTML));
  const btn = await el.click("unlock"); assert.deepStrictEqual(ev.find(x => x[0] === "toast"), ["toast", "Mot de passe requis", true], "champ vide : refus sans appel");
  el.fields["vlt-pass"] = { value: "s3cret" }; el.fields["vlt-inst"] = { value: "vw-ipro" }; ev.length = 0;
  await el.click("unlock"); assert.deepStrictEqual(sent.pop(), ["unlock", "vw-ipro", "s3cret"]); assert.strictEqual(el.fields["vlt-pass"].value, "", "le champ est vidé aussitôt");
  assert(ev.some(x => x[0] === "toast" && x[1] === "Coffre déverrouillé") && ev.some(x => x[0] === "reloadCheck" || (x[0] === "pull" && x[1] === "vault")), "après le geste : état relu, badge rafraîchi");
  el.fields["vlt-kpass"] = { value: "pp" }; el.fields["vlt-key"] = { value: "k1" };
  await el.enter("sshadd", { disabled: false, textContent: "" }); assert.deepStrictEqual(sent.pop(), ["sshAdd", "k1", "pp"], "Entrée dans le champ déclenche le geste");
  h.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur env : démarrage, blocs poussés, page, onglets, copie, verrous, démontage");
  console.log("\nTous les tests du domaine env passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
