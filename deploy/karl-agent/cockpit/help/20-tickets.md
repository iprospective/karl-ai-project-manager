# Tickets

Le panneau **🎫 tickets** recherche et ouvre les tickets du PM (fichiers
markdown structurés, synchronisés avec Redmine).

## Ouvrir une fiche

Clique un ticket pour sa **fiche** : titre, statut, description, dernière
activité, protocole de test, branche/MR, environnements, liens (dépend de /
bloque / lié), métriques (tokens, coût, temps).

- Le **titre** d'un ticket est cliquable partout où il apparaît → ouvre la fiche.
- Un lien **↗ Redmine** (`…/issues/<id>`) pointe vers le ticket dans le tracker.

## Cycle de vie (statuts NORMS)

Un ticket suit un flux : `nouveau` → `en_cours` → `a_tester_dev` /
`a_tester_demandeur` → `a_mep` → `ferme`. Les transitions synchronisent Redmine
et journalisent dans le `.log.md` du ticket.

La prise en charge (`en_cours`) implique l'auto-assignation. Les changements de
statut se font via les [commandes PM](commandes) ou la [file de test](tests).
