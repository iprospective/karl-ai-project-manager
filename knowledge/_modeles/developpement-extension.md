---
type: modele
created: 2026-10-27
ticket: RM3524
---

# Modèle — guide de développement d'extensions, par produit

Un guide par produit, **même nom partout** : `knowledge/<produit>/developpement.md` (Dolibarr :
module ; PrestaShop : module ; Redmine : plugin ; Nextcloud : app ; Roundcube : plugin…). Il répond
à une question : *comment écrire, déboguer, tester et livrer une extension de ce produit, sur les
versions que le parc fait tourner ?* La mise en production a son propre fichier (`mep.md`), l'env
de dev recettable le sien (`env-dev.md`) : le guide y renvoie, il ne les recopie pas.

## La règle qui fait la valeur du guide : chaque fait dit OÙ il a été vérifié

Une API change d'une version à l'autre ; un fait vrai en 24 est faux en 19, et un guide qui ne le
dit pas fait écrire du code qui casse en production. Donc :

- tout fait technique porte sa **provenance** : `(vérifié 24.0.2 — htdocs/core/lib/geturl.lib.php)` ;
- un fait **non vérifié** se dit tel : `(pratique courante, non vérifié ici)` — et se vérifie avant
  d'être utilisé pour une décision ;
- la **table de compatibilité** (§ 8) ne contient que des faits vérifiés, version par version : c'est
  elle qu'on lit avant de choisir une API.

Erreur qui a motivé la règle (RM3524) : « `getURLContent` ne connaît pas PATCH » — vrai en 19 à 22,
faux en 24. Dit sans version, c'était faux une fois sur deux.

## Les rubriques (dans cet ordre ; une rubrique vide dit « à documenter »)

1. **Fiche d'identité** — versions du parc (instances, versions, langage et runtime de chacune),
   versions couvertes par le guide, plage d'identifiants réservée s'il y en a une.
2. **Démarrer** — le générateur officiel (et quand ne pas l'utiliser), l'env de dev (`env-dev.md`),
   où vivent les dépôts, comment on nomme une extension.
3. **Structure d'une extension** — l'arborescence commentée, le descripteur, ce que chaque dossier
   contient.
4. **Points d'extension** — crochets, événements, onglets, menus, droits, réglages, API REST,
   widgets, tâches planifiées, schéma de base ; pour chacun : comment, et un exemple réel du parc.
5. **Cycle de vie** — installation, activation, mise à jour (le schéma), désactivation,
   désinstallation : ce qui est rejoué, ce qui est perdu.
6. **Déboguer** — journaux, barre de débogage, mode développement, débogueur pas à pas.
7. **Tester** — le cadre de tests officiel, les tests de parcours, la recette par un agent.
8. **Compatibilité entre versions** — table « API ou comportement → depuis / jusqu'à → vérifié dans ».
9. **Pièges** — chacun avec son symptôme, sa cause, sa parade et sa provenance (ticket).
10. **Livrer** — empaquetage, dépôt, MEP (renvoi à `mep.md`), publication.
11. **Sources** — documentation officielle, fichiers de référence dans le code du produit.

## À écrire

| Produit | Fichier | État |
|---|---|---|
| Dolibarr (module) | [dolibarr/developpement.md](../dolibarr/developpement.md) | écrit (RM3524) |
| PrestaShop (module) | `prestashop/developpement.md` | à écrire |
| Redmine (plugin) | `redmine/developpement.md` | à écrire |
| Nextcloud (app) | `nextcloud/developpement.md` | à écrire |
| Roundcube (plugin) | `roundcube/developpement.md` | à écrire |
