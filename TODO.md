# TODO — Système de gestion de tâches `iprospective`

> **Index greppable** des tâches et exigences sur le système lui-même.
> Fiches détail archivées dans [`TODO/archived/`](./TODO/archived/) (2026-06-15).
>
> **⚠ Index historique** : le suivi opérationnel vit désormais dans les **tickets PM**
> (Redmine + `tasks/RM*.md`). Chaque item ci-dessous pointe vers son ticket de reprise.
> Ne plus ajouter d'item ici — créer un ticket (`pm-task-add`).
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
> - Détail d'une fiche archivée : `ls TODO/archived/`

## À faire

_(aucun — créer un ticket, pas une ligne ici)_

## Réalisé / repris en tickets

- [x] `002` [#user-request #agents #meta] [Interface de gestion + supervision des agents](TODO/archived/002-management-interface.md) — repris en tickets : RM1679 (interface web PM), RM1873 (cockpit karl-agent v0, livré), RM1893 (cockpit tranche 1) — 2026-07-04
- [x] `003` [#user-request #redmine #gitlab #agents] [CLI projet `pm`](TODO/archived/003-pm-cli.md) — **livré** : CLI `mmi-pm` + scripts `pm-*` (RM1945, déménagement `.mmi-pm-core` 2026-06-16) — 2026-07-04
- [x] `006` [#user-request #redmine #docs #norms] [Publication des documents vers le Wiki Redmine](TODO/archived/006-wiki-redmine-sync.md) — **livré** : `pm-wiki-sync.py` / `pm-sync-push`, bidir + fold-back (RM1821, P1→P4) — 2026-07-04
- [x] `008` [#user-request #redmine #agents #scripts] [Multi-user env vars `.env`](TODO/archived/008-multi-user-env-vars.md) — repris en ticket : RM1681 (rename MAIN/PJ1 → KARL/CHEFPROJ1 + adaptation scripts) — 2026-07-04
- [x] `001` [#constraint #redmine #user-request] [Critères de valeur Redmine à préserver](TODO/archived/001-redmine-value-criteria.md) — contraintes intégrées aux NORMS (modules redmine-*) ; fiche archivée en référence — 2026-07-04
- [x] `004` [#norms #agents] Compléter `clients/lemathou/client/overview.md` — repris en ticket : RM2103 — 2026-07-04
- [x] `007` [#user-request #structure #norms] [Flatten `projects/clients/` → `projects/`](TODO/archived/007-flatten-projects-clients.md) — repris en ticket : [RM1668](https://tasks.iprospective.fr/issues/1668) — 2026-07-04
- [x] `005` [#norms #user-request] Symlink `/zfs/workspaces/perso/mathematicians-db/mmi-pm` créé — 2026-05-12 (workspace au chemin `/zfs/workspaces/perso/{slug}/` et non `/zfs/workspaces/{slug}/` ; nom de symlink renommé en v1.5.1 de `.pm` → `mmi-pm`)
