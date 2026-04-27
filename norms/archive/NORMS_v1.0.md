---
schema_version: "1.0"
updated: 2026-04-26
---

# Normes de gestion des tâches — v1.0

## Configuration globale

```yaml
gitlab:
  instance: https://gitlab.iprospective.fr
  ssh: gitlab@repos.iprospective.fr

redmine:
  instance: # défini par projet dans project.md
```

## Structure des dossiers

```
project-management/
  norms/
    NORMS.md                          # version courante (ce fichier)
    CHANGELOG.md                      # historique des évolutions
    archive/                          # snapshots des versions majeures
  projects/
    {nom-projet}/
      project.md
      tasks/
        RM{id}_{titre-kebab}.md       # tâche
        RM{id}_{titre-kebab}.log.md   # journal append-only
  templates/
    task.md
    project.md
```

## Nommage des fichiers

| Élément | Format |
|---|---|
| Tâche | `RM{id}_{titre-en-kebab-case}.md` |
| Journal | `RM{id}_{titre-en-kebab-case}.log.md` |
| Projet | `project.md` à la racine du dossier projet |

## Schéma frontmatter — Tâche

Voir `templates/task.md` pour le template complet.

### Champs obligatoires
`schema_version`, `redmine_id`, `title`, `type`, `creator`, `status`, `priority`, `created`

### Champs conditionnels
- `bug.*` — uniquement si `type: bugfix`
- `git.*` — si développement impliqué
- `test_url` — si environnement de test disponible
- `deploy_actions` — si déploiement nécessaire
- `close_reason` — obligatoire quand `status: ferme`

## Machine d'états

```
[a_etudier_chiffrer]
        │ estimation lancée
        ▼
[etude_chiffrage_en_cours]
        │ approuvé                  │ abandonné / hors périmètre
        ▼                           ▼
   [a_faire]                    [ferme]
        │ démarrage
        ▼
   [en_cours] ◄──────────────────────────┐
        │ soumis                         │ corrections faites
        ▼                                │
[a_tester_verifier]                      │
        │ problèmes trouvés              │
        ├──────────────► [a_corriger] ───┘
        │ validé
        ▼
    [ferme]
```

Règle : **toute transition vers `ferme` requiert un `close_reason`.**

### Transitions valides

| De | Vers | Condition |
|---|---|---|
| `a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `assigned_to` renseigné |
| `etude_chiffrage_en_cours` | `a_faire` | `estimate.*` complet |
| `etude_chiffrage_en_cours` | `ferme` | `close_reason` requis |
| `a_faire` | `en_cours` | — |
| `en_cours` | `a_tester_verifier` | — |
| `en_cours` | `a_etudier_chiffrer` | périmètre modifié |
| `a_tester_verifier` | `a_corriger` | note dans journal |
| `a_tester_verifier` | `ferme` | `close_reason: resolu` |
| `a_corriger` | `en_cours` | — |
| `* (tout état)` | `ferme` | `close_reason` requis |

## Valeurs énumérées

### type
`audit` | `feature` | `bugfix` | `refactoring` | `documentation` | `security` | `performance` | `infrastructure` | `research` | `maintenance` | `assistance`

### status
`a_etudier_chiffrer` | `etude_chiffrage_en_cours` | `a_faire` | `en_cours` | `a_tester_verifier` | `a_corriger` | `ferme`

### priority
`low` | `normal` | `high` | `urgent`

### close_reason
`resolu` | `abandonne` | `doublon` | `wont_fix` | `invalide` | `hors_perimetre`

### bug.reproducibility
`always` | `often` | `sometimes` | `rarely` | `never`

### estimate.difficulty
`low` | `medium` | `high` | `critical`

### pistes.type
`automation` | `amélioration` | `sécurité` | `performance` | `intégration` | `documentation`

### pistes.effort
`low` | `medium` | `high`

### roi.immediate_benefit / roi.monthly_benefit
`1` (négligeable) → `5` (critique)

## Journal (fichier .log.md)

Format append-only — ne jamais modifier rétroactivement. Chaque entrée :

```markdown
## 2026-04-26T14:32 — agent-scraper (claude-sonnet-4-6)
Tokens : 3 200 | Durée : 15 min

Résumé de ce qui a été fait...
```

## Versionning des normes

| Type | Exemple | Règle |
|---|---|---|
| Majeur | `1.0 → 2.0` | Changement breaking — snapshot archivé dans `archive/NORMS_v{M}.0.md` |
| Mineur | `1.0 → 1.1` | Ajout rétrocompatible — CHANGELOG suffit |
| Patch | `1.1 → 1.1.1` | Clarification — CHANGELOG suffit |
