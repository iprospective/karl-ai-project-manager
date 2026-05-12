# TODO — Système de gestion de tâches `iprospective`

> **Index greppable** des tâches et exigences sur le système lui-même.
> Détail dans [`TODO/`](./TODO/).
>
> **Distinction avec [`PISTES.md`](./PISTES.md)** :
> - `PISTES.md` = **explorations spéculatives** sur des évolutions de fond (patterns AI-natifs, refonte, etc.) — ne s'engage à rien.
> - `TODO.md` = **demandes / exigences / actions concrètes** à planifier ou réaliser. Plus opérationnel.
> - [`Changelog.md`](./Changelog.md) = **acté** (versions livrées).
>
> **Format ligne** : `` - [statut] ID `#priority:xxx` [tags] [titre](TODO/file.md) — résumé ``
>
> **Statuts** : `[ ]` à faire · `[~]` en cours · `[x]` réalisé (gardé, daté).
>
> **Priorités** (greppables) :
> `#priority:now` (interrompre) · `#priority:high` (prochaine vague) ·
> `#priority:normal` (défaut) · `#priority:low` (nice-to-have) · `#priority:someday` (parking).
>
> **Tags utiles pour grep** : `#user-request` · `#observed` · `#constraint`
> · `#redmine` · `#gitlab` · `#docs` · `#agents` · `#norms` · `#meta`
>
> **Recettes grep** :
> - Toutes les now/high : `grep -E '#priority:(now|high)' TODO.md`
> - Détail des entrées d'une priorité : `grep -l '#priority:high' TODO/*.md`

## À faire

### now

_(aucun)_

### high

- [ ] `002` `#priority:high` [#user-request #agents #meta] [Interface de gestion + supervision des agents](TODO/002-management-interface.md) — UI lecture/édition + supervision live des agents, archi MD-source + DB-index, phasage CLI → UI → live → métriques
- [ ] `003` `#priority:high` [#user-request #redmine #gitlab #agents] [CLI projet `pm`](TODO/003-pm-cli.md) — commandes depuis le workspace (task create/list/assign/close, project init), orchestration Redmine + MD + git

### normal

- [ ] `001` `#priority:normal` [#constraint #redmine #user-request] [Critères de valeur Redmine à préserver dans toute évolution](TODO/001-redmine-value-criteria.md) — collaboration, base docs searchable, com client : contraintes à respecter
- [ ] `004` `#priority:normal` [#norms #agents] Compléter `clients/lemathou/client/overview.md` — contacts, secteur, contexte
- [ ] `005` `#priority:normal` [#norms #user-request] Créer le symlink `/zfs/workspaces/mathematicians-db/.pm` quand le workspace projet existera

### low

_(aucun)_

### someday

_(aucun)_

## Réalisé

_(rien encore)_
