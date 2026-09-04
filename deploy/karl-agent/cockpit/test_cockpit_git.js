#!/usr/bin/env node
// Tests du domaine git migré (RM2889, L4). Porte les garanties de test_cockpit.js
// (RM2602, RM2605) sur les couches. Lancer : node deploy/karl-agent/cockpit/test_cockpit_git.js
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert");
const DIR = __dirname;
function fakeElement() {
  const listeners = []; let inner = "";
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, scrollTop: 5,
    addEventListener(t, f) { listeners.push([t, f]); },
    removeEventListener(t, f) { const i = listeners.findIndex(([a, b]) => a === t && b === f); if (i >= 0) listeners.splice(i, 1); },
    get listenerCount() { return listeners.length; },
    async click(action, sha) { const btn = { dataset: { action, sha } }; const target = { closest: (s) => (s === "[data-action]" ? btn : null) };
      for (const [t, f] of [...listeners]) if (t === "click") await f({ type: "click", target, stopPropagation() {} }); } };
}
(async () => {
  const { gitDiffLine, gitStatLabel } = await import(path.join(DIR, "src/models/git/gitDiff.js"));
  const { GitLogViewModel } = await import(path.join(DIR, "src/viewmodels/git/GitLogViewModel.js"));
  const { GitPatchViewModel } = await import(path.join(DIR, "src/viewmodels/git/GitPatchViewModel.js"));
  const { GitBranches, GitPatch, GitBody, GitPanel } = await import(path.join(DIR, "src/views/git/GitPanel.view.js"));
  const { ROUTES } = await import(path.join(DIR, "src/core/endpoints.js"));
  const { mountGitPanel } = await import(path.join(DIR, "src/controllers/git.controller.js"));

  assert.strictEqual(gitDiffLine("+ajout"), "add"); assert.strictEqual(gitDiffLine("-retrait"), "del");
  assert.strictEqual(gitDiffLine("@@ -1,4 +1,9 @@"), "hunk"); assert.strictEqual(gitDiffLine(" contexte"), "");
  assert.strictEqual(gitDiffLine("+++ b/x.py"), "fh", "+++ est un en-tête, pas un ajout");
  assert.strictEqual(gitDiffLine("--- a/x.py"), "fh"); assert.strictEqual(gitDiffLine("diff --git a/x b/x"), "fh");
  assert.strictEqual(gitDiffLine(null), "");
  assert(/2 fichiers/.test(gitStatLabel({ count: 2, added: 5, removed: 3, files: [] })));
  assert(/1 fichier ·/.test(gitStatLabel({ count: 1, added: 1, removed: 0, files: [] })));
  assert(/1 binaire/.test(gitStatLabel({ count: 1, added: 0, removed: 0, files: [{ binary: true }] })), "un binaire est signalé");
  assert(gitStatLabel(null).length);
  console.log("✓ git (RM2602) : coloration du patch, résumé, binaires signalés");

  // lecture seule : la table des routes ET le code des couches
  const gitRoutes = Object.entries(ROUTES).filter(([k]) => k.startsWith("git.")).map(([, r]) => r.current);
  assert.deepStrictEqual(gitRoutes.sort(), ["/git/diff", "/git/log", "/git/show"], "seules trois routes git, toutes en lecture");
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap(x => x.isDirectory() ? walk(path.join(d, x.name)) : [path.join(d, x.name)]);
  for (const f of walk(path.join(DIR, "src"))) assert(!/\/git\/(checkout|reset|stash|revert|commit|push)/.test(fs.readFileSync(f, "utf8")), f);
  console.log("✓ git (RM2602) : lecture seule, aucune action exposée");

  const log = { is_git: true, branch: "2605-x", cwd: "/w", origin: "gitlab:x", dirty: 2,
    commits: [{ sha: "a1", short: "a1", subject: "un", pushed: true, date: "2026-09-04T10:00:00", author: "m" },
              { sha: "b2", short: "b2", subject: "deux", pushed: false, merge: true, date: "2026-09-04T11:00:00", author: "m" }] };
  const vm = new GitLogViewModel(log, { sel: "b2", branches: ["2605-x", "dev"] });
  assert.strictEqual(vm.mode, "list"); assert.strictEqual(vm.count, "2605-x · 1 non poussé · 2 modifiés");
  assert.strictEqual(vm.commits()[1].cur, true); assert(/LOCAL/.test(vm.commits()[1].title));
  assert.strictEqual(new GitLogViewModel({ is_git: false, commits: [] }, {}).mode, "not_git");
  assert.strictEqual(new GitLogViewModel({ is_git: true, pm_data_repo: true, commits: [] }, {}).count, "aucun code");
  assert.strictEqual(new GitLogViewModel({ is_git: true, commits: [] }, {}).mode, "empty");
  console.log("✓ ViewModel git : modes, compteur d'en-tête, commit courant");

  const brs = String(GitBranches(["2605-x", "dev"], "2605-x"));
  assert(/2605-x/.test(brs) && /dev/.test(brs) && /class="pill ok"/.test(brs), "la branche COURANTE est distinguée");
  assert.strictEqual(String(GitBranches([], null)), ""); assert.strictEqual(String(GitBranches(null, null)), "");
  const body = String(GitBody(vm));
  assert(/gcommit local cur/.test(body) && /pas encore poussé/.test(body) && /<span class="pill">merge<\/span>/.test(body));
  assert(/data-action="show" data-sha="a1"/.test(body) && !/onclick=/.test(body), "gestes en data-action, zéro onclick");
  assert(/pas un dépôt git/.test(String(GitBody(new GitLogViewModel({ is_git: false, commits: [] }, {})))));
  assert(/pm-task-take/.test(String(GitBody(new GitLogViewModel({ is_git: true, pm_data_repo: true, commits: [] }, {})))));
  const patch = String(GitPatch(new GitPatchViewModel({ stats: { count: 1, added: 1, removed: 0, files: [{ path: "x.py", added: 1, removed: 0 }] }, patch: "+++ b/x.py\n+ok\n ctx", truncated: true, max_bytes: 2048 })));
  assert(/<span class="fh">\+\+\+ b\/x.py<\/span>/.test(patch) && /<span class="add">\+ok<\/span>/.test(patch) && /tronqué à 2 Ko/.test(patch));
  assert(/&lt;/.test(String(GitPatch(new GitPatchViewModel({ patch: "+<b>" })))), "patch échappé");
  assert(/attache une session…/.test(String(GitPanel({ vm: null }))));
  console.log("✓ vues git : branches, journal, patch coloré et échappé, panneau vide");

  const el = fakeElement(); const calls = []; const notes = [];
  const svc = { async log(sid, force) { calls.push(["log", sid, !!force]); return log; },
                async show(sid, sha) { calls.push(["show", sid, sha]); return { commit: { short: sha }, message: "msg\nplus", stats: { count: 0 }, patch: "" }; },
                async diff(sid, mode) { calls.push(["diff", sid, mode]); return { base: "dev", stats: { count: 0 } }; } };
  let sid = null; const opened = [];
  const h = mountGitPanel(el, { service: svc, attached: () => sid, branchesOf: () => ["dev"], notify: (m, e) => notes.push([m, !!e]), openCenter: (s, sha) => opened.push([s, sha]) });
  assert(/attache une session…/.test(el.innerHTML));
  await h.refresh(); assert.strictEqual(calls.length, 0, "sans session attachée, aucun appel");
  await el.click("diff-branch"); assert.deepStrictEqual(notes.pop(), ["Aucune session attachée", false]);
  sid = "rm2889";
  await h.refresh(true); assert.deepStrictEqual(calls.pop(), ["log", "rm2889", true]); assert(/2605-x · 1 non poussé/.test(el.innerHTML));
  await el.click("show", "b2"); assert.deepStrictEqual(calls.pop(), ["show", "rm2889", "b2"]);
  assert(/b2 — msg/.test(el.innerHTML) && /data-action="close"/.test(el.innerHTML) && /gcommit local cur/.test(el.innerHTML));
  await el.click("center", "a1"); assert.deepStrictEqual(opened.pop(), ["rm2889", "a1"]);
  await el.click("diff-worktree"); assert(/Travail non commité/.test(el.innerHTML) && /aucune différence/.test(el.innerHTML));
  h.reset(); assert(/attache une session…/.test(el.innerHTML) && h.state.log === null);
  h.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur git : session absente, journal, commit, centre, diff, reset, démontage");
  console.log("\nTous les tests du domaine git passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
