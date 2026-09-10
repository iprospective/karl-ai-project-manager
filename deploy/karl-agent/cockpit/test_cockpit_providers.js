#!/usr/bin/env node
// Tests du panneau Fournisseurs (RM3068) : le catalogue pilote les formulaires, une valeur de secret ne se
// préremplit JAMAIS et ne reste pas à l'écran, le rôle appartient au couple projet ↔ instance, gestes en data-*.
"use strict";
const fs = require("fs"); const path = require("path"); const assert = require("assert"); const DIR = __dirname;
const settle = () => new Promise(r => setTimeout(r, 5));
function fakeEl(id) { const L = []; let inner = ""; const kids = {}; const self = { id, style: {}, dataset: {}, value: "", checked: false, textContent: "", kids,
  get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, querySelector(s) { return kids[s] || null; }, querySelectorAll(s) { return kids["*" + s] || []; },
  replaceChildren(...n) { inner = n.map(x => x.outerHTML || x.textContent || "").join(""); }, addEventListener(t, f) { L.push([t, f]); }, removeEventListener() {},
  async click(action, data) { const n = { dataset: Object.assign({ action }, data || {}), closest: () => n }; for (const [t, f] of [...L]) if (t === "click") await f({ target: n, preventDefault() {}, stopPropagation() {} }); await settle(); } };
  return self; }
(async () => {
  const VM = await import(path.join(DIR, "src/modules/providers/ProvidersViewModel.js"));
  const V = await import(path.join(DIR, "src/modules/providers/Providers.view.js"));
  const { mountProviders } = await import(path.join(DIR, "src/modules/providers/providers.controller.js"));

  const cat = { axes: [{ axis: "task", label: "Tickets" }, { axis: "llm", label: "Modèles de travail" }], types: [
    { type: "redmine", axis: "task", label: "Redmine", fields: [{ name: "url", label: "URL", required: true, help: "" }], secrets: [{ key: "API_KEY", label: "Clé d'API" }] },
    { type: "ollama", axis: "llm", label: "Ollama", fields: [{ name: "url", label: "URL", required: true, help: "" }, { name: "model", label: "Modèle", required: false, help: "" }], secrets: [{ key: "API_KEY", label: "Clé" }] }] };
  const data = { user: "mathieu", admin: true, defaults: { task: "redmine-ipro", llm: "ollama-strix" },
    instances: [
      { name: "redmine-ipro", axis: "task", type: "redmine", local: false, fields: { url: "https://r.example" }, secrets: [{ key: "API_KEY", label: "Clé d'API", var: "REDMINE__REDMINE_IPRO__API_KEY", set: true }] },
      { name: "redmine-matnat", axis: "task", type: "redmine", local: true, fields: { url: "https://m.example" }, secrets: [{ key: "API_KEY", label: "Clé d'API", var: "REDMINE__REDMINE_MATNAT__API_KEY", set: false }] },
      { name: "ollama-strix", axis: "llm", type: "ollama", local: true, fields: { url: "http://strix.lan:11434", model: "qwen3:8b" }, secrets: [{ key: "API_KEY", label: "Clé", var: "LLM__OLLAMA_STRIX__API_KEY", set: false }] }],
    assignments: [{ client: "matnat", project: "infra", axis: "task", instance: "redmine-matnat", role: "primary", params: { project_id: 12 } },
                  { client: "iprospective", project: "pm-ai-agents", axis: "task", instance: "redmine-matnat", role: "secondary", params: {} }] };

  // — ViewModel —
  let vm = new VM.ProvidersViewModel({ cat, data });
  const axes = vm.axes();
  assert.deepStrictEqual(axes.map(a => a.axis), ["task", "llm"], "les axes du catalogue, dans l'ordre");
  assert.strictEqual(axes[0].instances.length, 2); assert(axes[0].instances[0].isDefault && !axes[0].instances[1].isDefault, "le défaut est marqué");
  const mat = axes[0].instances.find(i => i.name === "redmine-matnat");
  assert.deepStrictEqual(mat.uses.map(u => u.role), ["primary", "secondary"], "la MÊME instance est primaire ici et secondaire là");
  assert(mat.uses[0].project === "matnat/infra" && mat.uses[0].params === "project_id=12", "le projet et ses paramètres sont rendus");
  assert(mat.secrets[0].set === false && vm.axes()[0].instances[0].secrets[0].set === true, "l'état des clés, jamais leur valeur");
  assert(!JSON.stringify(vm.axes()).includes("value"), "aucun champ « value » ne circule dans le modèle");
  assert.deepStrictEqual(vm.formOf("ollama", { url: "http://x", model: "m" }).map(f => f.name + "=" + f.value), ["url=http://x", "model=m"], "le formulaire vient du catalogue");
  assert.strictEqual(vm.formOf("ollama", {})[0].value, "", "création : champs vides");
  console.log("✓ ViewModel : axes, défaut, état des clés, rôle par projet, formulaire piloté par le catalogue");

  // — vue —
  vm = new VM.ProvidersViewModel({ cat, data, open: "redmine-ipro" });
  const s = String(V.ProvidersCard(vm));
  assert(!/\son\w+=/.test(s), "aucun on* dans la vue");
  assert(/type="password"/.test(s) && /placeholder="saisir pour remplacer"/.test(s), "le secret se saisit, il ne s'affiche pas");
  assert(!/value="[^"]*"[^>]*data-role="secret"/.test(s) && !/data-role="secret"[^>]*value=/.test(s), "le champ de secret n'est JAMAIS prérempli");
  assert(/posée/.test(s) && /REDMINE__REDMINE_IPRO__API_KEY/.test(s), "l'état et le NOM de la variable sont montrés");
  assert(/data-action="secret-save"/.test(s) && /data-action="default"/.test(s) && /data-action="delete"/.test(s), "gestes en data-action");
  assert(/data-role="scope"/.test(s), "l'administrateur peut viser le .env global");
  assert(!/data-role="scope"/.test(String(V.ProvidersCard(new VM.ProvidersViewModel({ cat, data: { ...data, admin: false }, open: "redmine-ipro" })))), "un non-administrateur n'a pas l'option globale");
  assert(/Ollama/.test(String(V.ProvidersCard(new VM.ProvidersViewModel({ cat, data, open: "+llm" })))), "création : le formulaire propose les types de l'axe");
  console.log("✓ vue : secret en écriture seule, état affiché, gestes en data-*, option globale réservée à l'admin");

  // — contrôleur —
  const el = fakeEl("providerscard"); const envoyes = []; const champ = fakeEl("c"); const scope = fakeEl("s");
  el.kids['[data-role="secret"][data-name="redmine-ipro"][data-key="API_KEY"]'] = champ;
  el.kids['[data-role="scope"][data-name="redmine-ipro"][data-key="API_KEY"]'] = scope;
  const svc = { cat, data, load: async () => data, save: async (b) => { envoyes.push(["save", b]); return { ok: true }; },
                secret: async (b) => { envoyes.push(["secret", b]); return { ok: true }; }, assign: async () => ({}) };
  let confirme = true;
  const ctl = mountProviders(el, { service: svc, notify: () => {}, confirm: () => confirme });
  await ctl.load();
  champ.value = "s3cr3t-de-test";
  await el.click("secret-save", { name: "redmine-ipro", type: "redmine", key: "API_KEY" });
  const [kind, body] = envoyes[envoyes.length - 1];
  assert(kind === "secret" && body.value === "s3cr3t-de-test" && body.scope === "user", "la valeur part au serveur, portée « user » par défaut");
  assert.strictEqual(champ.value, "", "le champ est vidé aussitôt : la valeur ne reste pas à l'écran");
  assert(!String(el.innerHTML).includes("s3cr3t-de-test"), "et elle n'est jamais réaffichée");
  scope.checked = true; champ.value = "autre";
  await el.click("secret-save", { name: "redmine-ipro", type: "redmine", key: "API_KEY" });
  assert.strictEqual(envoyes[envoyes.length - 1][1].scope, "global", "la case « global » change la portée");
  confirme = false; await el.click("secret-unset", { name: "redmine-ipro", type: "redmine", key: "API_KEY" });
  assert(envoyes[envoyes.length - 1][1].unset === undefined, "effacer sans confirmation ne fait rien");
  confirme = true; await el.click("secret-unset", { name: "redmine-ipro", type: "redmine", key: "API_KEY" });
  assert(envoyes[envoyes.length - 1][1].unset === true, "effacer, confirmé");
  await el.click("default", { axis: "llm", name: "ollama-strix" });
  assert.deepStrictEqual(envoyes[envoyes.length - 1][1], { default_for: "llm", name: "ollama-strix" }, "définir le défaut d'un axe");
  confirme = true; await el.click("delete", { name: "redmine-matnat" });
  assert(envoyes[envoyes.length - 1][1].delete === true, "supprimer une déclaration, confirmé");
  console.log("✓ contrôleur : la valeur part et disparaît, portée globale, effacement confirmé, défaut, suppression");

  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/id="providerscard"/.test(html), "le panneau a son hôte dans les réglages");
  console.log("\nLe panneau Fournisseurs passe.");
})().catch(e => { console.error("✗", e.stack || e.message); process.exit(1); });
