#!/usr/bin/env node
// Test NAVIGATEUR du cockpit (RM2889) — le seul filet qui voit ce que node ne voit pas : « Illegal invocation » sur une fonction native
// détachée, une exception au restaurer des onglets épinglés, un module qui ne s'évalue pas dans Chromium/Firefox (incidents des 2026-09-05/06).
//
// Il sert la page et ses modules depuis ce dossier (aucun karl-agent requis ; /api/* répond 401 comme une instance à auth requise),
// sème le stockage local d'un utilisateur revenu (jeton, onglets épinglés de chaque sorte, préférences), charge la page dans un navigateur
// Playwright et exige : aucune erreur de page, `window.karl` posé, l'init passée (le premier /api/session/refresh part), l'écran de login
// affiché (401). OPTIONNEL : sans Playwright résolu (variable KARL_PLAYWRIGHT_DIR = un node_modules qui le contient), il se déclare ignoré
// et passe — les suites node restent le socle ; celui-ci est le complément à lancer avant une MEP du front.
// Lancer : KARL_PLAYWRIGHT_DIR=/chemin/vers/node_modules node deploy/karl-agent/cockpit/test_cockpit_browser.js
"use strict";
const fs = require("fs"); const path = require("path"); const http = require("http"); const assert = require("assert"); const { createRequire } = require("module");
const DIR = __dirname;
function resolvePlaywright() {
  const cands = [process.env.KARL_PLAYWRIGHT_DIR, path.join(DIR, "node_modules"), path.join(process.env.HOME || "", ".local/lib/node_modules")].filter(Boolean);
  for (const d of cands) { try { return createRequire(path.join(d, "/"))("playwright"); } catch (e) { /* suivant */ } }
  return null;
}
const pw = resolvePlaywright();
if (!pw) { console.log("↷ test navigateur ignoré : Playwright introuvable (KARL_PLAYWRIGHT_DIR=<node_modules> pour l'activer)"); process.exit(0); }
const MIME = { ".html": "text/html;charset=utf-8", ".js": "application/javascript; charset=utf-8", ".css": "text/css", ".json": "application/json" };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, "http://x");
  if (u.pathname === "/" || u.pathname === "/cockpit") { res.writeHead(200, { "Content-Type": MIME[".html"] }); return res.end(fs.readFileSync(path.join(DIR, "index.html"))); }
  if (u.pathname === "/api/session/cockpit-config") { res.writeHead(200, { "Content-Type": MIME[".json"] }); return res.end(JSON.stringify({ auth_required: true, login_enabled: true, monitors: [], layouts: [], actions: [], task_types: [], priorities: [], statuses: [] })); }
  if (u.pathname.startsWith("/api/")) { res.writeHead(401, { "Content-Type": MIME[".json"] }); return res.end(JSON.stringify({ error: "authentification requise" })); }
  if (u.pathname.startsWith("/static/")) {
    const rel = u.pathname.slice("/static/".length); const f = path.join(DIR, rel);
    if (fs.existsSync(f) && fs.statSync(f).isFile()) { res.writeHead(200, { "Content-Type": MIME[path.extname(f)] || "application/octet-stream" }); return res.end(fs.readFileSync(f)); }
    res.writeHead(200, { "Content-Type": MIME[".js"] }); return res.end("/* vendor absent du dépôt : stub */");
  }
  res.writeHead(404); res.end();
});
const seed = () => {
  localStorage.setItem("karlToken", "jeton-de-test"); localStorage.setItem("karlUser", "mathieu"); localStorage.setItem("karlAdmin", "1"); localStorage.setItem("karlDeviceId", "d1");
  localStorage.setItem("karlTabs", JSON.stringify([{ kind: "dash", key: "", label: "tableau de bord", pinned: true }, { kind: "review", key: "2889", label: "RM2889", pinned: true }, { kind: "project", key: "iprospective/pm-ai-agents", label: "pm-ai-agents", pinned: true }, { kind: "file", key: "x|/w|README.md", label: "README.md", pinned: true }, { kind: "panel", key: "settings", label: "réglages", pinned: true }]));
  localStorage.setItem("karlTabActive", "review:2889"); localStorage.setItem("karlPanel", "tickets"); localStorage.setItem("karlSet", "default"); localStorage.setItem("karlDynSort", "1");
  localStorage.setItem("karlCollapsed", JSON.stringify(["⋯ hors du jeu courant"])); localStorage.setItem("karlRight", JSON.stringify({ tab: "state", collapsed: false, manual: false })); localStorage.setItem("karlRightStartOpen", "1"); localStorage.setItem("karlRightDefaultTab", "outline");
  localStorage.setItem("karlThemeLocal", "dark"); localStorage.setItem("karlLeftCollapsed", "0"); localStorage.setItem("karlRightWidth", "400"); localStorage.setItem("karlOpened", JSON.stringify(["2889", "2807"]));
};
(async () => {
  await new Promise(r => server.listen(0, "127.0.0.1", r)); const url = "http://127.0.0.1:" + server.address().port + "/";
  for (const kind of (process.env.KARL_BROWSERS || "chromium").split(",")) {
    if (!pw[kind]) continue;
    let browser; try { browser = await pw[kind].launch({ headless: true }); } catch (e) { console.log("↷ " + kind + " indisponible : " + e.message.split("\n")[0]); continue; }
    for (const [label, seeded] of [["stockage vide", false], ["utilisateur revenu (jeton, onglets épinglés, préférences)", true]]) {
      const page = await browser.newPage(); const errors = []; const apiCalls = [];
      page.on("pageerror", e => errors.push(e.stack || e.message)); page.on("request", r => { if (/\/api\//.test(r.url())) apiCalls.push(new URL(r.url()).pathname); });
      if (seeded) await page.addInitScript(seed);
      await page.goto(url, { waitUntil: "load" }); await page.waitForTimeout(1500);
      const st = await page.evaluate(() => ({ karl: !!window.karl, version: window.karl && window.karl.version, gate: document.getElementById("authgate").className, lock: document.getElementById("lock").textContent, cmds: document.querySelectorAll("[data-cmd]").length }));
      assert.deepStrictEqual(errors, [], kind + " / " + label + " : erreur(s) de page :\n" + errors.join("\n"));
      assert(st.karl && st.version, kind + " / " + label + " : window.karl absent — boot.js ne s'est pas évalué");
      assert(apiCalls.includes("/api/session/cockpit-config") && apiCalls.some(p => p.startsWith("/api/session/refresh")), kind + " / " + label + " : l'init n'est pas allée jusqu'au premier tick (" + apiCalls.join(", ") + ")");
      assert.strictEqual(st.gate, "show", kind + " / " + label + " : 401 → l'écran de login doit être affiché");
      if (seeded) assert.strictEqual(st.lock, "🔓 mathieu (admin)", "l'état mémorisé est rendu (cadenas)");
      console.log("✓ " + kind + " — " + label + " : aucune erreur, boot évalué (v" + st.version + "), init jusqu'au premier tick, " + st.cmds + " commandes, écran de login");
      await page.close();
    }
    await browser.close();
  }
  server.close();
  console.log("\nLe cockpit se charge dans un vrai navigateur.");
})().catch(e => { console.error("✗", e.stack || e.message); server.close(); process.exit(1); });
