// Tests RM3497 — l'indicateur d'activité : ce qu'on montre, et ce qu'on tait.
//
// Le piège visé : un seuil par APPEL laisserait passer quinze appels de 150 ms,
// soit plus de deux secondes d'attente sans rien afficher. Le seuil porte donc sur
// la rafale. Ces tests le vérifient avec une horloge contrôlée — pas de sommeil
// réel, sinon la suite devient lente et instable.
"use strict";
const assert = require("assert");
const path = require("path");
const DIR = __dirname;

(async () => {
  const A = await import(path.join(DIR, "src/core/activity.js"));

  // Horloge et minuteur pilotés à la main.
  let t = 0;
  const timers = new Map();
  let idt = 1;
  A.configurerActivite({
    now: () => t,
    set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; },
    clear: (id) => timers.delete(id),
  });
  const avancer = (ms) => {
    t += ms;
    for (const [id, o] of [...timers]) if (o.quand <= t) { timers.delete(id); o.f(); }
  };

  const vus = [];
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  A.abonner((e) => vus.push({ ...e }));

  // 1. Une opération brève ne s'affiche jamais.
  let fin = A.debut("court");
  avancer(100);
  assert.strictEqual(A.activite().actif, false, "sous le seuil : rien");
  fin();
  assert.strictEqual(A.activite().nombre, 0, "et plus rien en cours");
  console.log("✓ une opération brève ne fait rien clignoter");

  // 2. Une opération longue s'affiche, avec son nom.
  fin = A.debut("timesheet/day");
  avancer(300);
  const e = A.activite();
  assert(e.actif, "au-delà du seuil : on montre");
  assert.strictEqual(e.libelle, "timesheet/day", "et on dit ce qu'on attend");
  fin();
  assert.strictEqual(A.activite().actif, false, "terminé : on se tait");
  console.log("✓ une opération longue se montre et se nomme");

  // 3. LE CAS VISÉ : des opérations brèves qui s'enchaînent SANS interruption.
  //    Quinze fois 150 ms, c'est 2,25 s d'attente — il faut le voir.
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  let courante = A.debut("appel 1");
  for (let i = 2; i <= 15; i++) {
    const suivante = A.debut("appel " + i);   // la suivante démarre AVANT la fin
    avancer(150);
    courante();
    courante = suivante;
  }
  assert(A.activite().actif,
         "une rafale ininterrompue d'appels brefs DOIT s'afficher : c'est tout l'enjeu");
  assert(A.activite().attente >= 2000, "l'attente cumulée est bien celle de la rafale");
  courante();
  assert.strictEqual(A.activite().actif, false, "la rafale finie, l'indicateur s'éteint");
  console.log("✓ quinze appels de 150 ms ne passent plus inaperçus");

  // 4. Le plus ancien est celui qu'on nomme.
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  const a = A.debut("vieux");
  avancer(50);
  const b = A.debut("jeune");
  avancer(300);
  assert.strictEqual(A.activite().libelle, "vieux", "on nomme ce qu'on attend depuis le plus longtemps");
  assert.strictEqual(A.activite().nombre, 2, "et on compte le reste");
  a(); b();
  console.log("✓ on nomme la plus ancienne, on compte les autres");

  // 5. Terminer deux fois ne décompte qu'une fois.
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  const c = A.debut("x");
  const d = A.debut("y");
  c(); c();
  assert.strictEqual(A.activite().nombre, 1, "une fin rejouée ne fausse pas le compte");
  d();
  console.log("✓ une fin rejouée ne fausse pas le compte");

  // 6. Une opération en échec se termine quand même.
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  await A.suivre(Promise.reject(new Error("boum")), "qui-echoue").catch(() => {});
  assert.strictEqual(A.activite().nombre, 0,
                     "un appel en échec ne laisse pas l'indicateur tourner pour toujours");
  console.log("✓ un échec n'immobilise pas l'indicateur");

  // 7. Un abonné qui lève n'empêche pas les autres d'être prévenus.
  A._reinitialiser();
  A.configurerActivite({ now: () => t, set: (f, d) => { const id = idt++; timers.set(id, { f, quand: t + d }); return id; }, clear: (id) => timers.delete(id) });
  let recu = 0;
  A.abonner(() => { throw new Error("abonné fautif"); });
  A.abonner(() => { recu++; });
  A.debut("z")();
  assert(recu > 0, "un abonné fautif ne prive pas les autres");
  console.log("✓ un abonné fautif ne bloque pas les autres");

  // 8. L'en-tête porte la zone, et la couche API déclare ses appels.
  const fs = require("fs");
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert(/id="activity"/.test(html) && /id="activity-txt"/.test(html),
         "l'en-tête porte la zone d'activité");
  assert(/hidden/.test(html.split('id="activity"')[1].slice(0, 120)),
         "et elle est cachée au départ");
  const api = fs.readFileSync(path.join(DIR, "src/core/api.js"), "utf8");
  assert(/from "\.\/activity\.js"/.test(api) && /suivre\(/.test(api),
         "tout appel serveur passe par le suivi : aucun module à modifier");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/abonner\(/.test(boot), "le boot branche l'affichage une fois");
  console.log("✓ page et câblage");

  console.log("\nTous les tests de l'indicateur d'activité passent.");
})().catch((e) => { console.error("✗", e.stack || e.message); process.exit(1); });
