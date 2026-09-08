# runtime·redmine-hygiene — description vivante, checklist, done_ratio
Ouvrir quand : le ticket a une checklist · sa description est périmée · son done_ratio évolue. Outil `pm-task-description-update`. Source : `norms/src/modules/redmine-hygiene.md`.

**La description Redmine = état courant de la demande** (mutable, « où on en est ») ; **les notes = événements datés** (append-only, « ce qui s'est passé »). Les deux se tiennent à jour : une checklist cochée seulement en note devient invisible ; une description initiale contredite par 12 notes est illisible.

**Mettre à jour la description (obligatoire) quand :**
1. elle contient un état qui a changé (statut en prose « en attente de validation client », URL d'env de test, version cible, décision provisoire) → la réécrire, pas seulement la contredire en note ;
2. elle contient une checklist / liste de tâches (`- [ ]`/`- [x]`, sous-objectifs, critères d'acceptation, étapes) → cocher/éditer DANS la description à chaque progression ;
3. demande explicite du demandeur ou d'un intervenant ;
4. re-cadrage substantiel en cours de travail (chemin, identifiant, cible, item ajouté/retiré après rédaction) → répercuter dans la description (référence de la vérification finale), pas juste une note « fix complémentaire » ; ex. `old/ → erp_old/old/` devenu `erp_old/dev/` : réécrire, + note « Description mise à jour suite re-cadrage : … ».

**Note accompagnante obligatoire** à chaque changement de description : quoi + pourquoi (« Description : coché items 3 et 4 (livraison faite, doc à jour) ») — Redmine ne diff pas les descriptions.

**`done_ratio` (Redmine) ↔ `completion_pct` (MD), au fil de l'eau** : par défaut ratio `cochées / total` arrondi de la checklist ; sinon évaluation de l'agent. Journalisé nativement par Redmine ⇒ pas de note dédiée (cocher un item = modif de description ⇒ note ; 50→75 % seul ⇒ pas de note).

**Outils** : `pm-task-description-update.py <id>` : `--check 1,2` / `--uncheck 3` / `--check-all`, `--done-ratio auto|<int>`, `--set-from-file <path>` (remplace tout) → PUT Redmine (`description` + `done_ratio` + `notes` si description changée) + sync MD (`completion_pct`, checklist) + `.log.md`. `pm-task-status-update` REFUSE `a_tester_demandeur`, `a_mep`, `ferme:resolu` s'il reste des items non cochés (`--allow-unchecked` si volontaire).
