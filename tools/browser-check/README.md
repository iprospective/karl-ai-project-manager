---
type: doc
created: 2026-09-11
---

# browser-check — valider une page au NAVIGATEUR (RM3036)

Charge une URL dans un Chromium headless, exécute un geste, lit la console et **constate
l'effet dans l'interface**. Sort en `0` si tout passe, `1` sinon : utilisable tel quel
comme ligne de protocole de test.

## Pourquoi cet outil existe

Le 2026-09-08 (RM3025), une modification front est partie en production sans passage
navigateur et a cassé l'ajout au panier de Calicote. Deux causes, **aucune visible en
test unitaire** :

1. un endpoint `addpalier` en **500** — il faut exécuter la requête pour le voir ;
2. le **bundle CCC non régénéré** — le fichier était déployé, la page ne le chargeait pas.

Un seul chargement de page les attrapait toutes les deux. L'outillage manquait, donc le
test n'a pas eu lieu : c'est ce trou-là qui est comblé ici, et la règle qui l'impose est
NORMS `testing` § 7 (site public ⇒ validation navigateur obligatoire).

## Installation

```bash
cd tools/browser-check && npm i        # playwright-core + puppeteer-core, gitignorés
```

Le **navigateur n'est pas téléchargé** : le script prend un Chromium déjà présent dans
`~/.cache/ms-playwright`, `~/.cache/puppeteer`, ou `/usr/bin`. S'il n'en trouve aucun —
ou si aucun pilote n'est installé — il **refuse de conclure** et le dit, plutôt que de
laisser croire à une validation qui n'a pas eu lieu.

## Usage

```bash
node tools/browser-check/browser-check.js --url <URL> [options]
```

| Option | Effet |
|---|---|
| `--expect-selector "<css>"` | échoue si le sélecteur est absent |
| `--click "<css>"` | clique, puis attend `--wait` ms |
| `--expect-change "<css>"` | échoue si ce contenu n'a **pas** changé après le clic (exige `--click`) |
| `--expect-text "<texte>"` | échoue si le texte est absent de la page rendue |
| `--wait <ms>` | attente après le clic (défaut 1500) |
| `--screenshot <f.png>` | capture pleine page, y compris en cas d'échec |
| `--allow-console-errors` | tolère une erreur JS (à justifier) |
| `--allow-missing-assets` | tolère un 404 de ressource (à justifier) |
| `--json` | sortie machine |

Une option mal tapée est une **erreur** (code 2), jamais un silence : un scénario
qui « passe » parce qu'un contrôle a été ignoré est pire que pas de test.

Les deux familles d'erreurs de console sont **séparées** — un asset 404 (déploiement
incomplet) n'est pas un plantage JS, et `--allow-console-errors` ne fait donc pas taire
le premier. C'est précisément la distinction qui manquait sur RM3025.

## Exemple — le scénario RM3025, rejoué

```bash
node tools/browser-check/browser-check.js \
  --url https://calicote-presta-2.test.iprospective.fr/fr/p/2025-cappelletti-farcis-sans-gluten-pasta-di-venezia \
  --expect-selector ".js-palier-form" \
  --click ".js-palier-form button[type=submit]" \
  --expect-change ".cart-products-count" \
  --wait 4000
```

```
ok   la page répond en 2xx/3xx
ok   sélecteur présent : .js-palier-form
ok   élément cliquable : .js-palier-form button[type=submit]
ok   clic effectué
ok   le contenu de « .cart-products-count » a changé
ok   toutes les ressources se chargent (assets déployés / bundle régénéré)
ok   aucune erreur JS en console
```

## Sur quel environnement ?

**L'env de recette du ticket**, celui que `pm-task-take` a monté : c'est le seul dont on
sait qu'il porte exactement la branche testée. Ne pas rsyncer vers une préprod partagée
pour « aller plus vite » — c'est ce qui a abîmé `calicote-presta-2.test` pendant RM3025.
La préprod ne sert qu'à la recette d'intégration, une fois la branche fusionnée.

## Structure

| Fichier | Rôle |
|---|---|
| `lib.js` | **logique pure** : analyse des options, choix du pilote et du Chromium, classement des erreurs, **verdict**. Aucune E/S. |
| `browser-check.js` | entrée : ouvre le navigateur, **observe** la page, délègue le verdict à `lib.js`. |
| `test_browser_check.js` | tests de `lib.js` — `node tools/browser-check/test_browser_check.js`, aucun Chromium requis. |

Le verdict est séparé de l'observation pour une raison simple : sans cette coupure, on ne
peut tester l'outil de test qu'en lançant un navigateur — donc on ne le teste pas.

## Mode parcours — plusieurs étapes, avec connexion (RM3359)

Un clic ne suffit pas à dérouler un tunnel de commande. Le mode parcours joue une suite
d'étapes décrites dans un fichier, et se rejoue avec des paramètres différents.

```bash
node tools/browser-check/browser-check.js --scenario parcours/tunnel.json \
  --param base=https://boutique.example --param paiement=virement \
  --secret-env motdepasse=BOUTIQUE_TEST_PASS
```

### Étapes disponibles

| Action | Clés | Effet |
|---|---|---|
| `goto` | `url` | charge la page (échoue hors 2xx/3xx) |
| `remplir` | `selecteur`, `valeur` | vide le champ et saisit |
| `choisir` | `selecteur`, `valeur` | sélectionne dans une liste |
| `cliquer` | `selecteur` (+ `apres` en ms) | clique et attend |
| `attendre` | `ms` | pause |
| `attendre-selecteur` | `selecteur` (+ `ms`) | attend l'apparition |
| `memoriser` | `selecteur` | relève l'état, pour le comparer ensuite |
| `verifier-selecteur` | `selecteur` | l'élément est là |
| `verifier-texte` | `texte` | le texte est dans la page |
| `verifier-change` | `selecteur` | le contenu a changé depuis `memoriser` |
| `capture` | `fichier` | copie d'écran |

### Ce que le mode garantit

- **Le parcours est validé EN ENTIER avant la première étape.** Une clé manquante à l'étape 10
  arrête tout avant l'étape 1 : s'interrompre au milieu d'un tunnel laisse un panier à moitié
  rempli et une base sale, ce qui disqualifie un test qu'on rejoue en série.
- **Un paramètre absent est une erreur**, jamais une chaîne vide. Un mot de passe vide donnerait
  « identifiants invalides », et on chercherait le bug dans le site.
- **Les secrets ne passent pas par la ligne de commande** (`ps` la rend lisible par tout le
  système) : `--secret-env cle=NOM_DE_VARIABLE` va les chercher dans l'environnement, et ils
  sont masqués dans les sorties, qu'on colle souvent dans un ticket.
- **On s'arrête à la première étape ratée**, avec son numéro, son motif et une capture d'écran.
  Enchaîner donnerait quinze échecs pour une seule cause.

### Exemple

```json
{
  "nom": "Ajout au panier depuis la fiche produit",
  "etapes": [
    { "action": "goto", "url": "{{base}}/fr/p/2025-un-produit" },
    { "action": "verifier-selecteur", "selecteur": ".js-palier-form" },
    { "action": "memoriser", "selecteur": ".cart-products-count" },
    { "action": "cliquer", "selecteur": ".js-palier-form button[type=submit]", "apres": 4000 },
    { "action": "verifier-change", "selecteur": ".cart-products-count" }
  ]
}
```
