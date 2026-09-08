> 📂 **Module `testing` — quand lire ceci :** je code ou modifie de la logique (fonction, règle, calcul, parsing, transition d'état, flux) · je livre un ticket · je rédige un protocole de test.
> **Outils :** `mmi-pm test`, `pm-task-protocol`, `pm-task-deliver` · **Préchargé par :** *(personne — ouvert à la demande via le déclencheur KERNEL, tripwire #17)*.

## Discipline de tests — coder, c'est livrer les tests avec le code

Référence **canonique** de la discipline de tests. Le principe fondateur (décision
Mathieu 2026-09-07) : **on n'écrit pas du code sans écrire ses tests, et on les écrit
AU FIL DE L'EAU** — pendant le dev, pas comme une dette à solder à la livraison. Un
changement livré **sans** les tests qui lui correspondent est incomplet.

Ce module détaille le **tripwire #17**. Il complète, sans les remplacer, le
protocole de test humain (`pm-task-protocol`, cf. `modules/redmine-hygiene.md`) et les
tests du cockpit exigés côté front (cf. `modules/git-mep.md`).

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
