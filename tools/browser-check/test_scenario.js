#!/usr/bin/env node
/* Tests RM3359 — logique pure du mode SCÉNARIO (aucun navigateur).
 *
 * Ce que ces tests protègent, et pourquoi chacun existe :
 *
 *  1. Un paramètre MANQUANT est une erreur, pas une chaîne vide. Un mot de passe absent
 *     remplacé par du vide donne « identifiants invalides » : on chercherait le bug dans le
 *     site pendant une heure avant de regarder la ligne de commande.
 *  2. Le scénario est validé EN ENTIER avant qu'une seule étape ne s'exécute. S'arrêter à
 *     l'étape 9 parce qu'une clé manque à la 10 laisse un panier à moitié rempli et une base
 *     sale — pour un test de non-régression qu'on rejoue en série, c'est disqualifiant.
 *  3. Une étape non observée ÉCHOUE. On ne déclare pas réussi ce qu'on n'a pas vu.
 *  4. Le rapport nomme l'étape fautive : un parcours de quinze étapes qui casse doit dire
 *     laquelle, sinon il ne vaut pas mieux qu'un « ça ne marche pas ».
 *  5. Les secrets sont masqués dans les sorties — on colle ces rapports dans des tickets.
 *
 * Lancer : node tools/browser-check/test_scenario.js
 */
"use strict";
const S = require("./scenario.js");

let fails = 0;
function check(nom, cond, detail) {
  console.log((cond ? "ok   " : "FAIL ") + nom + (cond || !detail ? "" : " — " + detail));
  if (!cond) fails++;
}

// ── substitution de paramètres ──────────────────────────────────────────────
let r = S.substituer("bonjour {{prenom}}", { prenom: "Paul" });
check("variable remplacée", r.valeur === "bonjour Paul" && r.manquantes.length === 0);
check("variable inconnue signalée, et laissée en place",
      (() => { const x = S.substituer("{{absente}}", {}); 
               return x.manquantes[0] === "absente" && x.valeur === "{{absente}}"; })());
check("plusieurs variables dans la même valeur",
      S.substituer("{{a}}-{{b}}", { a: "1", b: "2" }).valeur === "1-2");
check("une valeur vide fournie EXPRÈS n'est pas « manquante »",
      S.substituer("{{v}}", { v: "" }).manquantes.length === 0);
check("zéro est une valeur, pas une absence", S.substituer("{{n}}", { n: 0 }).valeur === "0");
check("accolade simple laissée tranquille (un sélecteur peut en contenir)",
      S.substituer("div{color}", {}).valeur === "div{color}");
check("texte sans variable inchangé", S.substituer("rien", {}).valeur === "rien");

// ── préparation : tout est validé AVANT d'exécuter ──────────────────────────
const parcours = {
  nom: "tunnel",
  etapes: [
    { action: "goto", url: "{{base}}/connexion" },
    { action: "remplir", selecteur: "#email", valeur: "{{email}}" },
    { action: "remplir", selecteur: "#passwd", valeur: "{{motdepasse}}" },
    { action: "cliquer", selecteur: "#SubmitLogin" },
    { action: "verifier-texte", texte: "Mon compte" },
  ],
};
let p = S.preparer(parcours, { base: "http://x.lxc", email: "a@b.c", motdepasse: "s3cr3t" });
check("parcours valide : aucune erreur", p.erreurs.length === 0, p.erreurs.join(" | "));
check("les variables sont substituées dans les étapes", p.etapes[0].url === "http://x.lxc/connexion");
check("le secret est substitué aussi", p.etapes[2].valeur === "s3cr3t");
check("chaque étape est numérotée", p.etapes.map((e) => e.numero).join(",") === "1,2,3,4,5");

p = S.preparer(parcours, { base: "http://x.lxc", email: "a@b.c" });  // mot de passe oublié
check("paramètre manquant => erreur nommant l'étape ET le paramètre",
      p.erreurs.some((e) => e.includes("étape 3") && e.includes("motdepasse")), p.erreurs.join(" | "));

p = S.preparer({ etapes: [{ action: "cliquer" }] }, {});
check("clé obligatoire absente => erreur", p.erreurs.some((e) => e.includes("« selecteur » manquant")));
p = S.preparer({ etapes: [{ action: "danser", selecteur: "#a" }] }, {});
check("action inconnue => erreur qui liste les actions valides",
      p.erreurs.some((e) => e.includes("action inconnue") && e.includes("cliquer")));
check("scénario vide => erreur", S.preparer({ etapes: [] }, {}).erreurs.some((e) => e.includes("vide")));
check("scénario absent => erreur, pas de plantage", S.preparer(null, {}).erreurs.length > 0);
p = S.preparer({ etapes: [{ action: "attendre", ms: "beaucoup" }] }, {});
check("attente non numérique => erreur", p.erreurs.some((e) => e.includes("ms")));
p = S.preparer({ etapes: [{ action: "attendre", ms: 500 }] }, {});
check("attente numérique acceptée", p.erreurs.length === 0, p.erreurs.join(" | "));
p = S.preparer({ etapes: [{ action: "goto", url: "{{a}}" }, { action: "cliquer" }] }, {});
check("TOUTES les erreurs sont rendues, pas seulement la première", p.erreurs.length === 2, p.erreurs.join(" | "));

// ── verdict d'étape ─────────────────────────────────────────────────────────
const e1 = S.preparer({ etapes: [{ action: "cliquer", selecteur: "#payer" }] }, {}).etapes[0];
check("étape observée réussie", S.verdictEtape(e1, { ok: true }).ok === true);
check("étape observée en échec", S.verdictEtape(e1, { ok: false }).ok === false);
check("étape NON observée => échec (pas de succès par défaut)", S.verdictEtape(e1, {}).ok === false);
check("le libellé porte le numéro et la cible",
      S.verdictEtape(e1, { ok: true }).nom === "1. cliquer #payer",
      S.verdictEtape(e1, { ok: true }).nom);

const e2 = S.preparer({ etapes: [{ action: "verifier-change", selecteur: "#panier" }] }, {}).etapes[0];
check("changement constaté => réussite", S.verdictEtape(e2, { avant: "0", apres: "1" }).ok === true);
check("contenu identique => échec", S.verdictEtape(e2, { avant: "0", apres: "0" }).ok === false);
check("rien observé des deux côtés => échec", S.verdictEtape(e2, {}).ok === false);
check("le détail montre avant/après",
      S.verdictEtape(e2, { avant: "0", apres: "1" }).detail.includes('avant="0"'));

// ── verdict global ──────────────────────────────────────────────────────────
let v = S.verdict([{ nom: "1. goto", ok: true }, { nom: "2. cliquer", ok: true }]);
check("tout réussi => parcours réussi", v.ok === true && v.echec === null);
v = S.verdict([{ nom: "1. goto", ok: true }, { nom: "2. cliquer", ok: false }, { nom: "3. verifier", ok: false }]);
check("un échec => parcours en échec", v.ok === false);
check("c'est la PREMIÈRE étape fautive qui est nommée", v.echec.nom === "2. cliquer");

// ── masquage des secrets ────────────────────────────────────────────────────
check("le secret est masqué dans le rapport",
      S.masquer("connexion avec s3cr3t refusée", ["s3cr3t"]) === "connexion avec •••• refusée");
check("plusieurs secrets masqués",
      S.masquer("a=motdepasse b=jeton42", ["motdepasse", "jeton42"]) === "a=•••• b=••••");
check("le même secret masqué partout où il apparaît",
      S.masquer("s3cr3t puis s3cr3t", ["s3cr3t"]) === "•••• puis ••••");
// Une chaîne très courte n'est pas masquée : « 1 » ou « ok » apparaissent partout, les masquer
// caviarderait le rapport au point de le rendre illisible — l'inverse du but.
check("valeur de 1 à 2 caractères laissée telle quelle",
      S.masquer("a=1 b=ok", ["1", "ok"]) === "a=1 b=ok");
check("aucun secret => texte inchangé", S.masquer("rien", []) === "rien");

console.log();
if (fails) { console.log("ÉCHEC (" + fails + ")"); process.exit(1); }
console.log("== OK ==");
