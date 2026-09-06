#!/usr/bin/env node
// Tests des domaines commandes PM (RM2211) et réglages/thème (RM2213, RM2386) migrés — RM2889, L5.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() {
  const L = []; let inner = ""; const nodes = {};
  return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true, nodes,
    querySelectorAll(sel) { return Object.values(nodes).filter(n => sel === "[data-arg]" && n.dataset.arg); },
    addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); },
    get listenerCount() { return L.length; },
    async fire(type, matchSel, n) { for (const [t, f] of [...L]) if (t === type) await f({ target: { closest: s => s === matchSel ? n : null } }); } };
}
(async () => {
  const { collectArgs } = await import(path.join(DIR, "src/modules/pmcmd/PmCommandsRepository.js"));
  const { PmMenuViewModel, PmFormViewModel } = await import(path.join(DIR, "src/modules/pmcmd/PmCommandsViewModel.js"));
  const { PmMenu, PmForm } = await import(path.join(DIR, "src/modules/pmcmd/PmCommands.view.js"));
  const { mountPmCommands } = await import(path.join(DIR, "src/modules/pmcmd/pmcmd.controller.js"));
  const { PmCommandsService } = await import(path.join(DIR, "src/modules/pmcmd/pmcmd.service.js"));
  const CMDS = [
    { name: "task-status", label: "Statut", category: "tickets", mutate: true, confirm: true, args: [
      { name: "rm_id", type: "rm_id", required: true, label: "Ticket" }, { name: "note", type: "text", max_len: 400, label: "Note" },
      { name: "statut", type: "enum", choices: ["a_faire", "en_cours"], label: "Statut" }, { name: "force", type: "bool", label: "Forcer" },
      { name: "project", type: "text", server: true }, { name: "fixed", type: "text", const: "x" }] },
    { name: "conso-report", label: "Conso", category: "métriques", args: [] }];
  const cats = new PmMenuViewModel({ commands: CMDS }).categories();
  assert.deepStrictEqual(cats.map(c => c.name), ["métriques", "tickets"], "catégories triées");
  assert.strictEqual(cats[1].commands[0].label, "✏ Statut"); assert(/confirmation requise/.test(cats[1].commands[0].title));
  const fields = new PmFormViewModel(CMDS[0]).fields();
  assert.deepStrictEqual(fields.map(f => f.widget), ["input", "textarea", "select", "checkbox"], "un widget par type ; server et const exclus");
  assert.strictEqual(fields[0].inputType, "number"); assert.strictEqual(fields[0].label, "Ticket *");
  const form = String(PmForm(new PmFormViewModel(CMDS[0])));
  assert(/id="pmf-rm_id" data-arg="rm_id" type="number"/.test(form) && /<textarea id="pmf-note"/.test(form) && /<select id="pmf-statut"/.test(form) && /type="checkbox" id="pmf-force"/.test(form));
  assert(/pill warn">mutation/.test(form) && /data-action="run" data-name="task-status"/.test(form) && !/onclick=/.test(form));
  assert(/<option value=""><\/option>/.test(form), "un enum facultatif offre l'option vide");
  assert(/pill">lecture/.test(String(PmForm(new PmFormViewModel(CMDS[1])))));
  assert(/data-action="pick" data-name="conso-report"/.test(String(PmMenu(new PmMenuViewModel({ commands: CMDS })))));
  assert.deepStrictEqual(collectArgs(CMDS[0], { rm_id: " 42 ", note: "", statut: "en_cours", force: true }), { args: { rm_id: "42", statut: "en_cours", force: true } }, "vide omis, bool vrai gardé, espaces retirés");
  assert.deepStrictEqual(collectArgs(CMDS[0], { rm_id: "", force: false }), { error: "Champ requis : Ticket" });
  console.log("✓ commandes PM (RM2211) : menu par catégorie, formulaire généré, arguments collectés");

  const runs = [];
  const svc = new PmCommandsService({ async all() { return CMDS; } }, async (name, args, opts) => { runs.push([name, args, opts]); return { ok: true, rc: 0, stdout: "fait\n", stderr: "" }; });
  const el = fakeElement(); const ev = [];
  const h = mountPmCommands(el, { service: svc, notify: (m, e) => ev.push([m, !!e]), confirm: (m) => { ev.push(["confirm", m]); return true; } });
  await h.load(); assert(/data-name="task-status"/.test(el.innerHTML), "catalogue rendu");
  await el.fire("click", "[data-action]", { dataset: { action: "pick", name: "task-status" } }); assert(/id="pmf-rm_id"/.test(el.innerHTML), "formulaire rendu au clic");
  el.nodes.rm = { dataset: { arg: "rm_id" }, value: "42" }; el.nodes.f = { dataset: { arg: "force" }, type: "checkbox", checked: true };
  const btn = { dataset: { action: "run", name: "task-status" }, disabled: false };
  await el.fire("click", "[data-action]", btn);
  assert.deepStrictEqual(runs.pop(), ["task-status", { rm_id: "42", force: true }, { confirm: true }], "pmRun reçoit les args collectés et la confirmation déclarée");
  assert(ev.some(x => x[0] === "confirm") && ev.some(x => x[0] === "✓ Statut"), "confirmation demandée, succès notifié");
  assert(/id="pm-result" class="logtail" style="margin-top/.test(el.innerHTML) && /fait/.test(el.innerHTML), "la sortie est affichée");
  h.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur commandes PM : catalogue, formulaire, exécution confirmée, sortie");

  const { theme } = await import(path.join(DIR, "src/modules/settings/SettingsRepository.js"));
  const { SettingsViewModel } = await import(path.join(DIR, "src/modules/settings/SettingsViewModel.js"));
  const { SettingsBody, ThemeCard } = await import(path.join(DIR, "src/modules/settings/Settings.view.js"));
  const { mountSettings } = await import(path.join(DIR, "src/modules/settings/settings.controller.js"));
  const mem = {}; const store = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; }, removeItem: k => { delete mem[k]; } };
  assert.deepStrictEqual(theme.read(store), { local: "", server: "auto" });
  theme.setServer(store, "dark"); theme.setLocal(store, "light"); assert.deepStrictEqual(theme.read(store), { local: "light", server: "dark" });
  assert(/Surcharge locale active \(effectif : light\)\. Conf serveur : dark\./.test(theme.hint(theme.read(store), "light")));
  theme.setLocal(store, "server"); assert.strictEqual(theme.read(store).local, "", "« server » efface la surcharge");
  assert(/Suit la conf serveur « dark »/.test(theme.hint(theme.read(store), "dark")));
  const tc = String(ThemeCard({ local: "light", hint: "h" })); assert(/<option value="light" selected>/.test(tc) && /data-theme-local/.test(tc) && !/onchange=/.test(tc));
  const SET = [{ key: "conf:ui.theme", group: "Design front", type: "enum", label: "Thème", value: "dark", options: ["auto", "dark", "light"] },
    { key: "roi", group: "Conf PM", type: "number", label: "Taux", value: 1.5, pinned: "PM_ROI" }, { key: "b", group: "Sessions", type: "bool", label: "Auto", value: true }, { key: "x", group: "Divers", type: "number", label: "X", value: 2 }];
  const groups = new SettingsViewModel({ settings: SET }).groups();
  assert.deepStrictEqual(groups.map(g => [g.name, g.open]), [["Design front", true], ["Conf PM", true], ["Sessions", true], ["Divers", false]]);
  const sb = String(SettingsBody(new SettingsViewModel({ settings: SET })));
  assert(/<option value="dark" selected>/.test(sb) && /data-setting="enum"/.test(sb) && /type="checkbox" style="width:auto" data-setting="bool" checked/.test(sb));
  assert(/🔒/.test(sb) && /disabled title="figé par PM_ROI \(\.env\)"/.test(sb), "un réglage figé par .env est grisé");
  assert(/data-key="x"[\s\S]*<button class="mini" data-action="save">💾/.test(sb) && !/onclick=|onchange=/.test(sb));
  const saved = []; const el2 = fakeElement(); const th = fakeElement(); const ev2 = [];
  const s2 = mountSettings(el2, th, { service: { settings: SET, async load() { return SET; }, async save(e, v) { saved.push([e.key, v]); return { ok: true, message: "✓", themeChanged: e.key === "conf:ui.theme" }; } },
    notify: (m) => ev2.push(m), confirm: () => true, storage: store, applyTheme: () => ev2.push("applyTheme"), effectiveTheme: () => "dark" });
  await s2.load(); assert(/data-key="conf:ui.theme"/.test(el2.innerHTML));
  const row = { dataset: { key: "conf:ui.theme" }, querySelector: () => null };
  await el2.fire("change", "[data-setting]", { dataset: { setting: "enum" }, value: "light", closest: () => row });
  assert.deepStrictEqual(saved.pop(), ["conf:ui.theme", "light"]); assert.strictEqual(mem.karlThemeServer, "light", "le thème serveur s'applique immédiatement (RM2386)"); assert(ev2.includes("applyTheme"));
  await th.fire("change", "[data-theme-local]", { value: "auto" }); assert.strictEqual(mem.karlThemeLocal, "auto"); assert(/<option value="auto" selected>/.test(th.innerHTML));
  s2.unmountAll(); assert.strictEqual(el2.listenerCount + th.listenerCount, 0);
  console.log("✓ réglages et thème (RM2213/RM2386) : groupes, figés, sauvegarde confirmée, thème immédiat");
  console.log("\nTous les tests réglages / commandes PM passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
