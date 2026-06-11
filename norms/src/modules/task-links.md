> 📂 **Module `task-links` — quand lire ceci :** je lie / fais dépendre / parente deux tickets.
> **Outils :** `pm-task-link` · **Préchargé par :** —.

## Liens entre tâches

Le frontmatter d'une tâche supporte plusieurs types de liens, chacun avec une
sémantique propre. Ces champs sont **symétrisés** (RM-id miroir maintenu côté
cible) et synchronisés avec les `relations` Redmine via le script
`scripts/pm-task-link.py`.

| Champ | Cardinalité | Sémantique | Miroir côté cible | Redmine `relation_type` |
|---|---|---|---|---|
| `parent_task` | `int \| null` | Hiérarchie : ce ticket a un parent | `sub_tasks` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `sub_tasks` | `list[int]` | Hiérarchie : enfants directs | `parent_task` (attribut `parent_issue_id`) | — (attribut d'issue) |
| `depends_on` | `list[int]` | Bloquant : A doit attendre B (B finit avant A) | `blocks` côté B | POST sur B : `blocks` → A |
| `blocks` | `list[int]` | Bloquant : A doit finir avant B (réciproque de `depends_on`) | `depends_on` côté B | POST sur A : `blocks` → B |
| `relates` | `list[int]` | **Lien latéral non-bloquant** : sujet/famille commun | `relates` côté cible | POST `relates` |
| `refs` | `list[obj]` | Référence externe libre (URL, commit, ticket partenaire) | — | — (champ libre, pas de relation Redmine) |

**Règles d'intégrité :**
- Tout lien `relates` / `depends_on` / `blocks` doit avoir son miroir côté cible.
  Si l'un est présent sans l'autre, c'est un drift à corriger via
  `pm-task-link sync <rm-id>`.
- `parent_task` est unique (au plus un parent par tâche).
- Un ticket ne peut pas se lier à lui-même.
- `pm-task-link rm` supprime les deux côtés.

**Sens des dépendances** : ne pas confondre. Si **A dépend de B**, alors
`A.depends_on = [B]` ET `B.blocks = [A]`. Côté Redmine, c'est une seule
relation `blocks` postée depuis B vers A.

### Hiérarchie parent/enfant (v1.20.3)

`parent_task` / `sub_tasks` ne sont **pas des relations Redmine** mais l'**attribut
natif d'issue `parent_issue_id`** (colonne « Redmine `relation_type` » = `—` dans le
tableau). Ils ne transitent donc pas par `/issues/<id>/relations.json` mais par un
`PUT parent_issue_id` sur l'enfant. La réflexion MD ↔ Redmine est outillée — **ne jamais
éditer ces champs à la main** :

| Geste | Commande | Effet |
|---|---|---|
| Créer un ticket enfant | `pm-task-add … --parent <RM>` | POST avec `parent_issue_id` + `parent_task` enfant + `sub_tasks` parent |
| (Re)poser / déplacer le parent d'un ticket existant | `pm-task-link parent <child> <parent>` | PUT Redmine + migre `sub_tasks` ancien→nouveau parent |
| Détacher | `pm-task-link parent <child> --unset` | PUT Redmine (parent vidé) + retire de `sub_tasks` du parent |
| Réconcilier depuis Redmine | `pm-task-sync <RM>` | lit `issue.parent.id` → `parent_task` + maintient les `sub_tasks` locaux |

Le cœur (réflexion frontmatter des deux côtés + logs) vit dans `scripts/pm_hierarchy.py`,
partagé par les trois scripts. Quand le parent n'est pas tracké localement (ticket
Redmine hors-PM), le champ enfant est posé mais `sub_tasks` n'est pas maintenu (no-op
silencieux, le lien Redmine reste correct).

**Règles d'intégrité hiérarchie :**
- `parent_task` est unique (au plus un parent par tâche).
- Pas d'auto-parent ni de cycle (Redmine refuse les cycles au PUT ; les scripts
  refusent l'auto-parent en amont).
- `sub_tasks` est dérivé : il doit toujours refléter l'ensemble des enfants dont le
  `parent_task` pointe vers ce ticket. En cas de drift, `pm-task-sync` sur l'enfant
  rétablit la cohérence.

