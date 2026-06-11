### Mise à jour de la description du ticket Redmine (obligatoire) — v1.13.0

La **description** d'un ticket Redmine (le corps principal, distinct des notes
de journal) est un document **vivant** : ce n'est pas un message figé à la
création, mais l'état courant de la demande. L'agent doit la maintenir à jour
chaque fois que son contenu cesse de refléter la réalité.

**Quatre déclencheurs obligent à mettre à jour la description** :

1. **La description contient des informations d'état qui ont changé** — par
   exemple un statut interne décrit en prose (« En attente de validation
   client », « bloqué par X »), une URL d'environnement de test, une version
   cible, une décision provisoire. Si la description affirme quelque chose qui
   n'est plus vrai, elle doit être réécrite, pas seulement contredite dans une
   note.
2. **La description contient une liste de tâches / une checklist** dont l'état
   évolue (cases cochées Markdown `- [ ]` / `- [x]`, sous-objectifs, critères
   d'acceptation, étapes restantes). À chaque progression, l'agent met à jour
   les cases ou items concernés **dans la description elle-même**, pas
   uniquement dans une note. La description sert de tableau de bord ; les notes
   servent à l'historique.
3. **Demande explicite** du demandeur ou d'un autre intervenant (« mets à jour
   la description avec X », « ajoute Y dans la description », reformulation
   demandée du périmètre, etc.).
4. **Modification substantielle de la demande en cours de travail** — quand
   le demandeur change un nom de chemin, un identifiant, une cible, ou
   ajoute/retire un item du périmètre **après** que la description a été
   rédigée. Le re-cadrage doit être répercuté dans la description (pas
   seulement traité dans une note de journal), car la description sert de
   référence pour la vérification finale. Ex : la description liste
   `old/ → erp_old/old/` mais le demandeur demande ensuite `erp_old/dev/` —
   réécrire la description avec `erp_old/dev/`, et accompagner d'une note
   « Description mise à jour suite re-cadrage : `erp_old/old` → `erp_old/dev` ».
   Ne **pas** se contenter d'une note « fix complémentaire » : si quelqu'un
   relit la description plus tard, il doit y voir l'état final, pas
   l'état initial.

**Note de journal accompagnante** : toute mise à jour de description doit être
accompagnée d'une note Redmine résumant **ce qui a changé** et **pourquoi**
(« Description : coché items 3 et 4 de la checklist (livraison faite, doc à
jour) »). Cela préserve la traçabilité — Redmine ne diff pas les descriptions
dans l'UI standard.

**Symétrie avec les notes** :
- **Note** = événement daté, append-only, raconte le « quoi s'est passé ».
- **Description** = état courant, mutable, raconte le « où on en est ».

Une checklist cochée uniquement dans une note (et pas dans la description) est
invisible dès qu'on scrolle ; une décision d'état figée dans la description
initiale et contredite par 12 notes successives est illisible. Les deux médias
sont complémentaires et **les deux doivent être tenus à jour**.

**% réalisé (`done_ratio`) au fil de l'eau** — v1.16.0 : l'agent maintient le
pourcentage de réalisation du ticket (`done_ratio` Redmine ↔ `completion_pct` MD)
**au fur et à mesure**, pas seulement à la clôture. La valeur se dérive :
- du **ratio de cases cochées** de la checklist quand il y en a une
  (`cochées / total`, arrondi) — c'est la règle par défaut ;
- sinon de l'**évaluation de l'agent** (avancement estimé du travail).

Le changement de `done_ratio` étant **journalisé nativement** par Redmine (comme
le statut, cf. v1.15.0), il ne donne **pas** lieu à une note dédiée. Une note
n'accompagne que les changements de **description** (texte/checklist), que Redmine
ne diff pas. Cocher un item de checklist EST une modification de description → note ;
faire passer le `done_ratio` de 50 à 75 → pas de note.

**Implémentation** (état v1.16.0) :
- **`pm-task-description-update.py <rm-id>`** : coche/décoche la checklist
  (`--check 1,2`, `--uncheck 3`, `--check-all`), met à jour `done_ratio`
  (`--done-ratio auto` depuis la checklist, ou un entier), ou remplace toute la
  description (`--set-from-file`). PUT Redmine (`description` + `done_ratio` +
  `notes` si la description a changé) + sync MD (`completion_pct` + checklist du
  corps) + append `.log.md`. C'est le wrapper de référence.
- **`pm-task-status-update.py`** refuse de passer une tâche en `a_tester_demandeur`,
  `a_mep` ou `ferme:resolu` s'il reste des items de checklist **non cochés** dans la
  description (`--allow-unchecked` pour outrepasser si c'est volontaire). Garde-fou
  pour ne pas livrer/clore avec une checklist non tenue à jour.

