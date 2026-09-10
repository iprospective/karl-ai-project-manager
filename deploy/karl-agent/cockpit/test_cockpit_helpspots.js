// Tests RM3075 — repères d'aide « ? » sur les zones du cockpit.
//
// La garde qui compte est la DERNIÈRE : un repère qui pointe une page d'aide disparue, ou une
// section renommée, est pire que pas de repère — il promet une explication et rend une page vide.
// Elle lit les vrais `help/*.md`, donc elle casse le jour où quelqu'un renomme un chapitre.
//
// Le reste vérifie ce qui casserait en silence : un repère posé deux fois (le worklog se re-rend à
// chaque tick), un repère qui survit à la décoche, un clic qui n'ouvre rien.
// Lancer : node test_cockpit_helpspots.js
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import { HELP_SPOTS, SPOT_ATTR, spotHtml, spotById, spotTopics, spotsEnabled, setSpotsEnabled } from "./src/modules/doc/helpSpots.js";
import { mountHelpSpots } from "./src/modules/doc/helpspots.controller.js";

// ── un faux DOM, juste ce que le contrôleur touche ──────────────────────────
function el(id, cls) {
  const node = {
    id: id || "", className: cls || "", children: [], html: "", parentElement: null, textContent: "",
    querySelector(sel) { return find(node, sel, true)[0] || null; },
    querySelectorAll(sel) { return find(node, sel, false); },
    // insertion RÉELLE : le contrôleur relit ensuite le DOM pour ne pas reposer deux fois —
    // un faux DOM qui se contente d'empiler du texte testerait autre chose que la vraie idempotence.
    insertAdjacentHTML(where, h) {
      node.html += h; node.where = where;
      const id = (h.match(/data-helpspot="([^"]+)"/) || [])[1] || "";
      const b = el("", ""); b.tag = "button"; b.attrs = { "data-helpspot": id }; b.parentElement = node;
      node.children[where === "afterbegin" ? "unshift" : "push"](b);
    },
    remove() { const p = node.parentElement; if (p) p.children = p.children.filter(c => c !== node); },
    closest() { return null; }, scrollIntoView() { node.scrolled = true; },
  };
  return node;
}
function find(root, sel, one) {
  const out = [];
  const want = String(sel).split(",").map(s => s.trim());
  const match = (c, w) => {
    const m = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(w);
    if (m) return c.attrs && c.attrs[m[1]] !== undefined && (m[2] === undefined || c.attrs[m[1]] === m[2]);
    return [c.id ? "#" + c.id : "", c.className ? "." + c.className : "", c.tag || ""].includes(w);
  };
  const walk = (n) => {
    for (const c of n.children) {
      if (want.some(w => match(c, w))) { out.push(c); if (one) return true; }
      if (walk(c)) return true;
    }
    return false;
  };
  walk(root);
  return out;
}
function doc() {
  const root = el("root");
  const add = (id, cls, tag) => { const n = el(id, cls); n.tag = tag || ""; n.parentElement = root; root.children.push(n); return n; };
  root.spotsPosed = () => root.querySelectorAll("[data-helpspot]").length;
  root.listeners = {};
  root.addEventListener = (t, fn) => { (root.listeners[t] = root.listeners[t] || []).push(fn); };
  root.removeEventListener = (t, fn) => { root.listeners[t] = (root.listeners[t] || []).filter(f => f !== fn); };
  // les zones du registre, telles qu'elles existent dans index.html
  for (const s of HELP_SPOTS) {
    const sel = s.sel.split(",")[0].trim();
    add(sel.startsWith("#") ? sel.slice(1) : "", sel.startsWith(".") ? sel.slice(1) : "");
  }
  return root;
}

// ── registre bien formé ─────────────────────────────────────────────────────
assert.ok(HELP_SPOTS.length >= 10, "le registre couvre les zones principales");
const ids = HELP_SPOTS.map(s => s.id);
assert.strictEqual(new Set(ids).size, ids.length, "identifiants de zone uniques");
for (const s of HELP_SPOTS) {
  assert.ok(s.sel && s.topic && s.tip, "chaque zone a un sélecteur, une page et une phrase : " + s.id);
  assert.ok(/[.!?…]$|\w$/.test(s.tip.trim()) && s.tip.length > 25, "la phrase dit à quoi la zone SERT : " + s.id);
  assert.ok(["h2", "summary", "first"].includes(s.where || "first"), "point d'insertion connu : " + s.id);
}
assert.strictEqual(spotById("worklog").topic, "worklog");
assert.strictEqual(spotById("inexistant"), null);

// ── rendu du repère ─────────────────────────────────────────────────────────
const h = spotHtml(spotById("worklog"));
assert.ok(/class="helpq hspot"/.test(h) && /data-helpspot="worklog"/.test(h), "classe et identifiant");
assert.ok(/aria-label="Aide/.test(h) && /<button/.test(h), "un bouton, annoncé — pas un span décoratif");
assert.ok(!/\son(click|mouse)\w*=/.test(h), "aucun gestionnaire inline");

// ── pose : idempotente, réversible ──────────────────────────────────────────
const d = doc();
const ctl = mountHelpSpots(d, { storage: null, later: (fn) => { fn(); return 1; }, observer: null });
const n1 = d.spotsPosed();
assert.ok(n1 >= 10, "les repères sont posés sur les zones présentes (" + n1 + ")");
ctl.apply();
assert.strictEqual(d.spotsPosed(), n1, "seconde passe : rien n'est posé deux fois (le worklog se re-rend à chaque tick)");

// ── préférence : par défaut visible, décochable, persistée ──────────────────
const mem = { m: {}, getItem(k) { return k in this.m ? this.m[k] : null; }, setItem(k, v) { this.m[k] = String(v); } };
assert.strictEqual(spotsEnabled(mem), true, "affichés par défaut : ils servent à qui ne connaît pas l'écran");
setSpotsEnabled(mem, false);
assert.strictEqual(spotsEnabled(mem), false, "la décoche est retenue");
assert.strictEqual(spotsEnabled({ getItem() { throw new Error("bloqué"); } }), true, "stockage indisponible : le cockpit marche quand même");

const d2 = doc();
const ctl2 = mountHelpSpots(d2, { storage: mem, later: (fn) => { fn(); return 1; }, observer: null });
assert.strictEqual(d2.querySelectorAll("[" + SPOT_ATTR + "]").length, 0, "préférence décochée : aucun repère posé");
assert.strictEqual(ctl2.toggle(true), true);
assert.ok(d2.spotsPosed() >= 10, "recochée : les repères reviennent sans rechargement");

// ── le clic ouvre la bonne page ─────────────────────────────────────────────
const opened = [];
const d3 = doc();
mountHelpSpots(d3, { storage: null, later: (fn) => { fn(); return 1; }, observer: null, openHelp: (t) => { opened.push(t); return Promise.resolve(); } });
const fire = (id) => (d3.listeners.click || []).forEach(fn => fn({
  target: { closest: (sel) => (sel === "[" + SPOT_ATTR + "]" ? { getAttribute: () => id } : null) },
  preventDefault() {}, stopPropagation() {},
}));
fire("worklog"); fire("cdc");
assert.deepStrictEqual(opened, ["worklog", "cdc"], "chaque repère ouvre SA page");
fire("zone-qui-nexiste-pas");
assert.strictEqual(opened.length, 2, "un identifiant inconnu n'ouvre rien et ne casse rien");

// ── LA garde : les pages et les sections citées existent vraiment ───────────
const HELP = path.join(path.dirname(new URL(import.meta.url).pathname), "help");
const pages = new Map();
for (const f of fs.readdirSync(HELP).filter(f => f.endsWith(".md"))) {
  const slug = f.replace(/\.md$/, "");
  const id = /^\d\d-/.test(slug) ? slug.slice(3) : slug;
  pages.set(id, fs.readFileSync(path.join(HELP, f), "utf8"));
}
for (const topic of spotTopics()) {
  assert.ok(pages.has(topic), "la page d'aide « " + topic + " » existe (help/NN-" + topic + ".md)");
}
const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim();
for (const s of HELP_SPOTS.filter(s => s.anchor)) {
  const titles = (pages.get(s.topic).match(/^#{1,4} .*$/gm) || []).map(t => norm(t.replace(/^#+ /, "")));
  assert.ok(titles.some(t => t.includes(norm(s.anchor))),
    "la section « " + s.anchor + " » existe dans la page « " + s.topic + " » (sinon le clic tombe sur une page qui ne répond pas)");
}
assert.ok(norm(pages.get("worklog")).includes("tableau de bord de la session"),
  "l'aide dit que le worklog est le tableau de bord de la session");

console.log("✓ repères d'aide (RM3075) : registre, pose idempotente, préférence, clic, et pages/sections citées vérifiées");
