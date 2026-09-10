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
    for (const [label, seeded, viewport] of [["stockage vide", false, null], ["utilisateur revenu (jeton, onglets épinglés, préférences)", true, null], ["mobile 390 px (RM3003)", false, { width: 390, height: 800 }]]) {
      const page = viewport ? await (await browser.newContext({ viewport })).newPage() : await browser.newPage(); const errors = []; const apiCalls = [];
      page.on("pageerror", e => errors.push(e.stack || e.message)); page.on("request", r => { if (/\/api\//.test(r.url())) apiCalls.push(new URL(r.url()).pathname); });
      if (seeded) await page.addInitScript(seed);
      await page.goto(url, { waitUntil: "load" }); await page.waitForTimeout(1500);
      const st = await page.evaluate(() => ({ karl: !!window.karl, version: window.karl && window.karl.version, gate: document.getElementById("authgate").className, lock: document.getElementById("lock").textContent, cmds: document.querySelectorAll("[data-cmd]").length }));
      assert.deepStrictEqual(errors, [], kind + " / " + label + " : erreur(s) de page :\n" + errors.join("\n"));
      assert(st.karl && st.version, kind + " / " + label + " : window.karl absent — boot.js ne s'est pas évalué");
      assert(apiCalls.includes("/api/session/cockpit-config") && apiCalls.some(p => p.startsWith("/api/session/refresh")), kind + " / " + label + " : l'init n'est pas allée jusqu'au premier tick (" + apiCalls.join(", ") + ")");
      assert.strictEqual(st.gate, "show", kind + " / " + label + " : 401 → l'écran de login doit être affiché");
      if (seeded) assert.strictEqual(st.lock, "🔓 mathieu (admin)", "l'état mémorisé est rendu (cadenas)");
      // RM3005 : les six stores nommés existent dès le boot et karl.stats() les compte
      const stores = await page.evaluate(() => window.karl.stats().stores.map(s => s.name + ":" + s.max));
      for (const want of ["session.registry:300", "ticket.mergecheck:200", "ticket.resolve:500", "ticket.sessions:200", "ticket.transitions:100", "ticket.usage:200"]) assert(stores.includes(want), kind + " / " + label + " : store " + want + " attendu dans karl.stats() (" + stores.join(", ") + ")");
      // RM3011 : une exception non rattrapée tombe dans le journal du front, et le badge de l'en-tête la compte
      const jl = await page.evaluate(() => { setTimeout(() => { throw new Error("boum de test"); }, 0); return new Promise(r => setTimeout(() => r({ n: window.karl.log.entries().filter(e => e.level === "error" && /boum de test/.test(e.msg)).length, badge: document.getElementById("ln-journal").textContent }), 300)); });
      assert(jl.n === 1 && jl.badge === "1", kind + " / " + label + " : l'erreur injectée doit être dans karl.log et comptée par le badge (" + JSON.stringify(jl) + ")");
      // RM3003 : le gabarit suit la largeur — une colonne à la fois et la barre du bas sur un écran étroit, rien de tout ça au bureau
      const lay = await page.evaluate(() => { const vis = (sel) => { const e = document.querySelector(sel); return !!e && getComputedStyle(e).display !== "none"; }; return { layout: document.documentElement.dataset.layout, page: document.querySelector("main").dataset.mpage, mnav: vis("#mnav"), left: vis("main > .left"), right: vis("main > .right"), cols: getComputedStyle(document.querySelector("main")).gridTemplateColumns.split(" ").length }; });
      if (viewport) {
        assert(lay.layout === "mobile" && lay.mnav && lay.cols === 1 && (lay.left !== lay.right), kind + " / " + label + " : gabarit mobile attendu, une colonne à la fois (" + JSON.stringify(lay) + ")");
        // sans jeton, le boot ouvre 🔧 réglages (page centre) : on part explicitement de la page « panneaux »
        const leftP = await page.evaluate(() => { document.querySelector('#mnav [data-mpage="left"]').click(); const vis = (sel) => getComputedStyle(document.querySelector(sel)).display !== "none"; return { page: document.querySelector("main").dataset.mpage, left: vis("main > .left"), right: vis("main > .right"), active: document.querySelector("#mnav .mnav-btn.active").dataset.mpage }; });
        assert(leftP.page === "left" && leftP.left && !leftP.right && leftP.active === "left", kind + " : page panneaux (" + JSON.stringify(leftP) + ")");
        const after = await page.evaluate(() => { document.querySelector('#mnav [data-mpage="center"]').click(); const vis = (sel) => getComputedStyle(document.querySelector(sel)).display !== "none"; return { page: document.querySelector("main").dataset.mpage, left: vis("main > .left"), right: vis("main > .right"), rpanel: vis("#rpanel") }; });
        assert(after.page === "center" && !after.left && after.right && !after.rpanel, kind + " : la barre du bas montre le centre seul (" + JSON.stringify(after) + ")");
        const rightP = await page.evaluate(() => { document.querySelector('#mnav [data-mpage="right"]').click(); const vis = (sel) => getComputedStyle(document.querySelector(sel)).display !== "none"; return { page: document.querySelector("main").dataset.mpage, rpanel: vis("#rpanel"), rnav: vis("#rpanel .rnav"), w: document.querySelector("#rpanel").getBoundingClientRect().width }; });
        assert(rightP.page === "right" && rightP.rpanel && rightP.rnav && rightP.w >= 380, kind + " : la page droite déplie la colonne sur toute la largeur (" + JSON.stringify(rightP) + ")");
        await page.goto(url + "?layout=desktop", { waitUntil: "load" }); await page.waitForTimeout(600);
        assert.strictEqual(await page.evaluate(() => document.documentElement.dataset.layout), "desktop", kind + " : ?layout=desktop force le bureau sur un écran étroit");
      } else assert(lay.layout === "desktop" && !lay.mnav && lay.left && lay.right && lay.cols === 2, kind + " / " + label + " : bureau attendu (" + JSON.stringify(lay) + ")");
      console.log("✓ " + kind + " — " + label + " : aucune erreur, boot évalué (v" + st.version + "), init jusqu'au premier tick, " + st.cmds + " commandes, écran de login, gabarit " + lay.layout);
      await page.close();
    }
    await browser.close();
  }
  server.close();
  console.log("\nLe cockpit se charge dans un vrai navigateur.");
})().catch(e => { console.error("✗", e.stack || e.message); server.close(); process.exit(1); });
