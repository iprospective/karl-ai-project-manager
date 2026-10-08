/* browser-check — SCÉNARIO : logique pure d'un parcours multi-étapes (RM3359).
 *
 * Le mode d'origine (RM3036) charge une page, clique un élément, vérifie. Assez pour empêcher
 * qu'une modification front reparte cassée en production ; pas assez pour dérouler un tunnel de
 * commande, où il faut se connecter, remplir des champs, enchaîner des pages et choisir un mode
 * de paiement.
 *
 * Tout ce qui se décide sans navigateur se décide ici : lecture du scénario, substitution des
 * paramètres, validation des étapes, verdict. L'exécution ne fait qu'obéir.
 *
 * Un scénario est un objet : { nom, etapes: [ {action, …}, … ] }.
 */
"use strict";

/** Actions reconnues, et pour chacune les clés qu'elle EXIGE. */
const ACTIONS = {
  "goto":            ["url"],
  "remplir":         ["selecteur", "valeur"],
  "choisir":         ["selecteur", "valeur"],   // <select>
  "cliquer":         ["selecteur"],
  "attendre":        ["ms"],
  "memoriser":       ["selecteur"],   // prend l'état d'un élément, pour le comparer plus tard
  "attendre-selecteur": ["selecteur"],
  "verifier-selecteur": ["selecteur"],
  "verifier-texte":  ["texte"],
  "verifier-change": ["selecteur"],
  "capture":         ["fichier"],
};

//: Une valeur `{{nom}}` est remplacée par le paramètre `nom`. Deux accolades, jamais une :
//: un sélecteur CSS peut contenir une accolade, un scénario n'a pas à s'en méfier.
const RX_VAR = /\{\{([a-z0-9_]+)\}\}/gi;

/**
 * Remplace les `{{variables}}` d'une chaîne par les paramètres donnés.
 * Une variable inconnue est une ERREUR, jamais une chaîne vide : un mot de passe manquant
 * remplacé par du vide donnerait « identifiants invalides », et on chercherait le bug ailleurs.
 *
 * @returns {{valeur: string, manquantes: string[]}}
 */
function substituer(chaine, params) {
  const manquantes = [];
  const valeur = String(chaine === undefined || chaine === null ? "" : chaine)
    .replace(RX_VAR, (tout, nom) => {
      const v = (params || {})[nom];
      if (v === undefined || v === null) {
        manquantes.push(nom);
        return tout;
      }
      return String(v);
    });
  return { valeur, manquantes };
}

/**
 * Valide et prépare un scénario : substitue les paramètres, vérifie chaque étape.
 * Rien n'est exécuté tant que TOUT est valide — un parcours qui s'arrête à l'étape 9 parce
 * qu'une clé manquait à l'étape 10 laisse un panier à moitié rempli et une base sale.
 *
 * @returns {{etapes: object[], erreurs: string[], nom: string}}
 */
function preparer(scenario, params) {
  const erreurs = [];
  const sc = scenario || {};
  const brutes = Array.isArray(sc.etapes) ? sc.etapes : [];
  if (!brutes.length) {
    erreurs.push("scénario vide : aucune étape");
  }
  const etapes = brutes.map((e, i) => {
    const num = i + 1;
    const etape = Object.assign({}, e);
    const action = etape.action;
    if (!ACTIONS[action]) {
      erreurs.push(`étape ${num} : action inconnue « ${action} » (attendu : ${Object.keys(ACTIONS).join(", ")})`);
      return etape;
    }
    for (const cle of ACTIONS[action]) {
      if (etape[cle] === undefined || etape[cle] === "") {
        erreurs.push(`étape ${num} (${action}) : « ${cle} » manquant`);
      }
    }
    // substitution sur toutes les valeurs textuelles de l'étape
    for (const cle of Object.keys(etape)) {
      if (typeof etape[cle] !== "string") continue;
      const { valeur, manquantes } = substituer(etape[cle], params);
      etape[cle] = valeur;
      for (const m of manquantes) {
        erreurs.push(`étape ${num} (${action}) : paramètre « ${m} » non fourni`);
      }
    }
    if (action === "attendre" && !(Number(etape.ms) > 0)) {
      erreurs.push(`étape ${num} : « ms » doit être un nombre positif`);
    }
    etape.numero = num;
    return etape;
  });

  return { nom: String(sc.nom || "scénario"), etapes, erreurs };
}

/**
 * Libellé d'une étape pour le rapport. Un parcours de quinze étapes qui casse doit dire
 * LAQUELLE et sur quoi — sinon le rapport ne vaut pas mieux qu'un « ça ne marche pas ».
 */
function libelle(etape) {
  const cible = etape.selecteur || etape.url || etape.texte || etape.fichier || etape.ms || "";
  return `${etape.numero}. ${etape.action}${cible !== "" ? " " + cible : ""}`
    + (etape.valeur !== undefined && etape.action !== "remplir" ? ` = ${etape.valeur}` : "");
}

/**
 * Verdict d'une étape à partir de ce qui a été observé.
 * `observe` : {ok, detail, avant, apres}. Une étape non observée est un ÉCHEC, jamais un
 * succès par défaut : on ne déclare pas réussi ce qu'on n'a pas vu.
 */
function verdictEtape(etape, observe) {
  const o = observe || {};
  if (etape.action === "memoriser") {
    return { nom: libelle(etape), ok: o.ok === true, detail: o.detail || "" };
  }
  if (etape.action === "verifier-change") {
    return {
      nom: libelle(etape),
      ok: o.avant !== o.apres && o.avant !== undefined,
      detail: `avant=${JSON.stringify(o.avant === undefined ? null : o.avant)}`
            + ` après=${JSON.stringify(o.apres === undefined ? null : o.apres)}`,
    };
  }
  return { nom: libelle(etape), ok: o.ok === true, detail: o.detail || "" };
}

/** Le parcours est réussi si toutes les étapes le sont. Rend aussi la première qui a cassé. */
function verdict(resultats) {
  const echec = (resultats || []).find((r) => !r.ok) || null;
  return { ok: !echec, echec, etapes: resultats || [] };
}

/**
 * Masque les valeurs sensibles d'un rapport : un mot de passe passé en paramètre ne doit pas
 * ressortir dans une sortie que l'on colle dans un ticket.
 */
function masquer(texte, secrets) {
  let out = String(texte === undefined || texte === null ? "" : texte);
  for (const s of secrets || []) {
    if (s && String(s).length > 2) {
      out = out.split(String(s)).join("••••");
    }
  }
  return out;
}

module.exports = { ACTIONS, substituer, preparer, libelle, verdictEtape, verdict, masquer };
