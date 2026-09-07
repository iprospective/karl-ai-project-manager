# Journal

**📜 journal** (menu du haut) affiche ce que le cockpit a consigné, côté **serveur**
(`karl-agent`) et côté **navigateur**, dans une même liste horodatée.

## Ce qu'on y voit

Chaque entrée porte une **sévérité** — `debug`, `info`, `warn`, `error` — et une
**catégorie** qui dit de quoi elle parle : `auth` (connexions, jetons), `issue`
(tickets), `provider` (Redmine, GitLab…), `tmux` (sessions d'agents), `claude`
(moteurs), `worklog`, `files`, `api` (requêtes), `mail`, `sets` (jeux de sessions),
`refresh`, `pm` (auto-commit et rattrapage git), `session`, `voice`, `env`, `front`
(le navigateur) et `system`.

- **serveur** (`srv`) : les événements du service — une session lancée ou fermée,
  une commande PM jouée, une commande tmux qui échoue, une requête refusée…
- **front** (`front`) : ce que le navigateur a rencontré — une exception non
  rattrapée, une promesse rejetée, un domaine qui a trébuché au montage. Les `warn`
  et `error` du navigateur sont aussi **remontés au serveur** : ils apparaissent dans
  le journal du service, même après avoir fermé l'onglet.

## Filtrer, suivre, copier

- **sévérité** : le seuil minimal affiché (`warn` = avertissements et erreurs).
- **catégories** : des puces à cocher ; « toutes » remet à zéro.
- **rechercher** : plein texte sur le message et ses champs.
- **⏸ pause / ▶ suivre** : tant que le panneau est visible, il relit le serveur toutes
  les 5 s et défile vers le bas ; la pause fige la liste pour lire.
- **⟳** relit tout le journal serveur ; **⎘ copier** met les entrées affichées dans le
  presse-papier (utile pour un ticket) ; **✕ front** vide le journal du navigateur
  (le serveur garde le sien).

Le badge du bouton **📜** compte les avertissements et erreurs arrivés depuis la
dernière ouverture du panneau.

## Côté serveur

Le fichier est `logs/karl-agent.jsonl` à la racine du repo PM (une ligne JSON par
entrée, rotation par taille, rétention 14 jours par défaut). En ligne de commande :
`mmi-pm log-tail --cat pm --level warn`. Réglages par variables d'environnement
`KARL_JOURNAL_DIR` / `_LEVEL` / `_MAX_MB` / `_KEEP_DAYS`.
