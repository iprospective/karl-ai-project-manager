#!/usr/bin/env node
// Tests RM3070 L2 — les préférences du navigateur sont cloisonnées par utilisateur.
// Un poste partagé mélangeait les réglages de deux développeurs, et une déconnexion laissait
// ceux du précédent en place. Sans utilisateur connecté (mono), rien ne doit changer.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;

function fakeStorage(init = {}) {
  const m = new Map(Object.entries(init));
  return { get length() { return m.size; }, key(i) { return [...m.keys()][i]; },
           getItem(k) { return m.has(k) ? m.get(k) : null; }, setItem(k, v) { m.set(k, String(v)); },
           removeItem(k) { m.delete(k); }, _m: m };
}

(async () => {
  const { createPrefs, IDENTITE } = await import(path.join(DIR, "src/core/prefs.js"));

  // 1. sans utilisateur : aucune clé ne bouge (mono — personne ne se connecte)
  let base = fakeStorage(); let p = createPrefs(base, () => "");
  p.setItem("tri", "date");
  assert.strictEqual(base.getItem("tri"), "date", "sans utilisateur, la clé reste nue");
  console.log("✓ mono : pas d'utilisateur, pas de préfixe — aucune préférence perdue à la mise à jour");

  // 2. avec utilisateur : la clé est cloisonnée, et l'autre ne la voit pas
  base = fakeStorage(); let qui = "alice"; p = createPrefs(base, () => qui);
  p.setItem("tri", "date");
  assert.strictEqual(base.getItem("u:alice:tri"), "date", "la clé est préfixée");
  assert.strictEqual(base.getItem("tri"), null, "rien n'est écrit sous la clé nue");
  qui = "bob";
  assert.strictEqual(p.getItem("tri"), null, "bob ne voit pas le réglage d'alice");
  p.setItem("tri", "nom");
  qui = "alice";
  assert.strictEqual(p.getItem("tri"), "date", "…et celui d'alice est intact");
  console.log("✓ deux développeurs sur le même navigateur ne se marchent plus dessus");

  // 3. l'identité de CE navigateur n'est jamais préfixée (sinon jeton introuvable au chargement)
  for (const k of IDENTITE) { p.setItem(k, "x"); assert.strictEqual(base.getItem(k), "x", k + " reste nu"); }
  console.log("✓ jeton, appareil, utilisateur, admin : clés nues — elles désignent la session, pas des goûts");

  // 4. adoption des préférences d'avant le cloisonnement
  base = fakeStorage({ plis: "1,2" }); p = createPrefs(base, () => "alice");
  assert.strictEqual(p.getItem("plis"), "1,2", "la préférence d'hier est adoptée");
  assert.strictEqual(base.getItem("u:alice:plis"), "1,2", "…et recopiée sous la clé cloisonnée");
  assert.strictEqual(base.getItem("plis"), "1,2", "…sans effacer l'original (cockpit antérieur encore utilisable)");
  console.log("✓ migration douce : le premier connecté garde ses réglages");

  // 5. purge à la déconnexion : les siennes seulement
  base = fakeStorage({ "u:alice:tri": "date", "u:alice:plis": "1", "u:bob:tri": "nom", karlToken: "t" });
  p = createPrefs(base, () => "alice");
  assert.strictEqual(p.purge(), 2, "deux préférences effacées");
  assert.strictEqual(base.getItem("u:bob:tri"), "nom", "celles de bob restent");
  assert.strictEqual(base.getItem("karlToken"), "t", "l'identité n'est pas touchée : c'est la déconnexion qui s'en charge");
  assert.strictEqual(createPrefs(base, () => "").purge(), 0, "sans utilisateur, la purge ne touche à rien");
  assert.strictEqual(p.purge("bob"), 1, "on peut purger un utilisateur nommé (déconnexion : l'identité est déjà effacée)");
  console.log("✓ déconnexion : les préférences de celui qui part, et elles seules");

  // 6. un stockage indisponible (mode privé) ne fait pas tomber le cockpit
  assert.strictEqual(createPrefs(null), null, "pas de stockage → pas de prefs, l'appelant sait déjà faire avec null");
  const cassé = { get length() { return 0; }, key() { return null; },
                  getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("quota"); }, removeItem() { throw new Error("x"); } };
  const pc = createPrefs(cassé, () => "alice");
  assert.strictEqual(pc.getItem("tri"), null); pc.setItem("tri", "x"); pc.removeItem("tri");
  assert.strictEqual(pc.purge(), 0);
  console.log("✓ stockage refusé (navigation privée, quota) : on continue sans, jamais d'exception");

  console.log("\nLe cloisonnement des préférences passe.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
