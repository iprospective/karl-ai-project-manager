> 📂 **Module `testing` — quand lire ceci :** je code ou modifie de la logique (fonction, règle, calcul, parsing, transition d'état, flux) · je livre un ticket · je rédige un protocole de test.
> **Outils :** `mmi-pm test`, `pm-task-protocol`, `pm-task-deliver` · **Préchargé par :** *(personne — ouvert à la demande via le déclencheur KERNEL, tripwire #17)*.

## Discipline de tests — coder, c'est livrer les tests avec le code

Référence **canonique** de la discipline de tests. Le principe fondateur (décision
Mathieu 2026-09-07) : **on n'écrit pas du code sans écrire ses tests, et on les écrit
AU FIL DE L'EAU** — pendant le dev, pas comme une dette à solder à la livraison. Un
changement livré **sans** les tests qui lui correspondent est incomplet.

Ce module détaille le **tripwire #17**. Il complète, sans les remplacer, le
protocole de test humain (`pm-task-protocol`, cf. `modules/status-workflow-pratique.md`) et les
tests du cockpit exigés côté front (cf. `modules/testing.md` § Front et cockpit).

### 1. TDD par défaut (quand c'est applicable)

Sur la **logique déterministe** — fonction pure, règle métier, calcul, parsing,
mapping, **transition d'état**, condition de bord — écrire le test **avant ou pendant**
le code, jamais seulement après. Le test EXPRIME l'intention ; l'implémentation la
satisfait. C'est le mode par défaut, pas l'exception : dès qu'un comportement peut
s'énoncer en « entrée → sortie attendue », il se code en test d'abord.

### 2. Tests unitaires systématiques

Toute logique métier porte des tests unitaires. **Extraire la logique en fonctions
pures** pour la rendre testable sans I/O est la première réponse à « c'est dur à
tester » (pattern déjà en place dans le repo PM : `scripts/test_pm_*.py`, `build_alerts`
testée hors HTTP). Le code difficile à tester est d'abord un **code à refactorer**, pas
un code à ne pas tester.

### 3. Tests fonctionnels / workflow / intégration — anticipés dès la conception

Au-delà de l'unité, couvrir les **parcours** et les **enchaînements** : une transition
de statut et **ses effets** ; un hook et **son effet** ; un flux applicatif de bout en
bout (ex. ajout au panier, MEP → notification) ; l'intégration entre deux composants.
Ces cas se **listent dès la conception** (« quels parcours ce dev crée/modifie ? ») et
leurs tests se codent **au fil de l'eau**, pas reconstitués après coup.

### 4. Couvrir TOUS les cas de figure

Un dev **énumère** ses cas et les **couvre** : nominal, **bornes/limites**, **erreurs**
et entrées invalides, **non-régression** sur l'existant qu'il touche. « Couvrir tous les
cas » vaut pour les **tests automatisés** ET pour le **protocole de test** (recette
humaine) : les deux sont **complémentaires**, pas exclusifs — le protocole décrit ce
qu'un humain vérifie, les tests auto verrouillent ce qu'une machine rejoue à chaque
changement. Un cas énoncé au protocole qui **peut** être automatisé **doit** l'être.

### 5. Outillage

- `mmi-pm test` : suite de tests du repo — **verte avant toute livraison**.
- **Front / cockpit touché** ⇒ tests cockpit (node) exigés dans la **même MR** (cf.
  `modules/git-mep.md` et la doc vivante de `modules/governance.md`).
- `pm-task-deliver` (`--check-all`) : gate de livraison — la livraison **atteste** que
  les tests adaptés au type de changement existent et passent.
- `pm-task-protocol` : le protocole de test humain, rédigé **au fil de l'eau** lui aussi
  (miroir frontmatter `test_protocol` lu par la fiche cockpit).

> **Trou d'outillage connu (à ticketer si absent) :** un contrôle **automatique** de
> *présence* de tests adaptés au type de changement, à brancher sur `pm-task-deliver` /
> `modules/status-workflow.md` (gate de MEP). Tant qu'il n'existe pas, l'attestation
> reste **déclarative** — mais l'obligation, elle, tient (tripwire #17).

### 6. Pragmatisme — le seul motif valable de « pas de test auto »

Certains comportements ne sont **pas** automatisables raisonnablement : rendu visuel
navigateur, interaction JS/DOM réelle, intégration tierce non simulable (ERP, passerelle
mail/SMS). Dans ces cas **uniquement** : **protocole de recette humaine** + **justification
tracée** (dans le ticket : quoi, pourquoi non automatisable). Jamais « pas de test » tout
court. « C'est dur à tester » n'est pas une justification — c'est un signal de refactor
(§2). La justification décrit une **impossibilité technique réelle**, pas une difficulté.

### 7. Site PUBLIC : le navigateur n'est pas optionnel (RM3036)

Sur un projet dont le meta porte **`browser_test: true`** — un site public, exposé à des
clients — **toute modification du rendu front se valide au NAVIGATEUR avant livraison**.
Pas « si on a le temps » : avant.

Ce n'est pas une précaution théorique. Le 2026-09-08 (RM3025), une modification front est
partie en production sans passage navigateur et **a cassé l'ajout au panier**. Deux causes,
qu'un seul chargement de page aurait attrapées : un endpoint en erreur 500 (classe appelée
en nom court, exception non rattrapée) et un **bundle CCC non régénéré** — le nouveau JS
n'était pas servi. Aucun test unitaire ne pouvait les voir : l'un ne se produit qu'à
l'exécution HTTP réelle, l'autre n'existe que dans l'assemblage des assets.

Ce que « validé au navigateur » exige, au minimum :

1. la page se **charge** sur l'environnement de recette (code HTTP 200, pas seulement
   « le fichier est déployé ») ;
2. le **geste** modifié est réellement exécuté (cliquer le bouton, soumettre le formulaire),
   pas seulement observé dans le source ;
3. la **console** du navigateur est lue : une erreur JS ne remonte nulle part ailleurs ;
4. l'**effet** est constaté dans l'interface (le panier passe de 0 à 1, le prix change),
   pas déduit de la base ;
5. après déploiement, la **purge du cache** et la régénération des assets sont vérifiées —
   sinon on teste l'ancien code sans le savoir.

Un pilotage **headless** satisfait ces cinq points et se rejoue : c'est la forme à
privilégier, et elle transforme la recette en test conservable. À défaut, recette humaine
tracée — mais sur un site public, l'absence de tout passage navigateur n'est **pas** une
option, et ne se couvre pas par la clause de pragmatisme du §6.

**L'outil existe, il n'y a plus d'excuse d'outillage** :

```bash
cd tools/browser-check && npm i          # une fois par machine
node tools/browser-check/browser-check.js --url <URL> \
     --expect-selector "<css>" --click "<css>" --expect-change "<css>"
```

Il rend `0`/`1`, cite l'erreur fautive, et **distingue un asset 404 d'un plantage JS** —
la distinction qui manquait sur RM3025. Détail : `tools/browser-check/README.md`.

**Sur quel environnement** : celui du ticket, monté par `pm-task-take`, seul dont on
sache qu'il porte exactement la branche testée. **Ne pas rsyncer vers une préprod
partagée** pour aller plus vite : pendant RM3025 c'est ainsi que `clienta-presta-2.test`
a été altérée, et l'environnement de recette d'un autre ticket avec. La préprod sert à la
recette d'intégration, après fusion.

L'option se pose avec `pm-project-config --client <c> --project <p> --browser-test true`,
et se lit dans le meta du projet : un agent qui livre du front sur un tel projet doit
vérifier ce drapeau **avant** de conclure que ses tests suffisent.

## Invariant ou tendance : ce qui casse un test, ce qui se notifie

Un test **échoue** pour dire « ceci est cassé, maintenant ». Il n'est pas fait pour dire
« ceci dérive depuis six semaines ». La confusion coûte cher : un échec rouge permanent
cesse d'être lu, et il entraîne à ignorer **tous** les rouges de la suite — c'est le
constat de RM2749, vérifié une seconde fois par RM2756.

Le partage :

- **Invariant** — une condition qui doit être vraie à chaque commit, dont la violation
  rend le système faux ou bloqué : plafond dépassé, index périmé, règle perdue, appel à
  un nom qui n'existe pas. **Le test casse**, et on répare avant de livrer.
- **Tendance** — une mesure qui glisse lentement et qu'on veut voir venir : une marge qui
  s'entame, une taille qui enfle, une péremption qui approche. **Ça se notifie**
  (`pm_notify`, via un travail de `jobs.reference.yml`), ça ne rougit pas la suite.

Le capteur de tendance n'ouvre pas non plus un **ticket** à chaque passage : un ticket est
une décision de travail, pas un canal d'alerte. Il émet une notification au **message
stable** — les chiffres en champs, jamais dans le texte — de sorte qu'une dérive qui dure
produise une entrée qui remonte, et non une par jour. Le ticket vient après, si l'humain
décide qu'il y a du travail.

Exemple de référence : `pm-context-budget --check` (invariant : le plafond) et
`pm-context-budget --notify` (tendance : la marge de 10 %), travail `norms-budget-watch`.
