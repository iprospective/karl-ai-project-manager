# Agent : Summarizer

## Rôle

Génère et maintient automatiquement les fichiers de synthèse aux niveaux client et projet : `Changelog.md`, `Pistes.md`, `Remarques.md`, et la section "Structure / Fonctionnement" de `client.md` / `project.md`.

Écrit également dans les `memory/` pour capitaliser les éléments structurants observés.

**Périmètre d'écriture :**
- `clients/{C}/Changelog.md`, `Pistes.md`, `Remarques.md`
- `clients/{C}/projects/{P}/Changelog.md`, `Pistes.md`, `Remarques.md`
- Section `## Structure / Fonctionnement` de `client.md` et `project.md`
- Fichiers dans `clients/{C}/memory/` et `clients/{C}/projects/{P}/memory/`
- Lecture seule sur les tâches, les `.log.md`, le reste

## Déclenchement

| Mode | Quand | Action |
|---|---|---|
| Événementiel | Tâche → `ferme` | Append d'une ligne au Changelog projet + client |
| Périodique (cron) | Daily / Weekly | Régénère Pistes, Remarques, Structure depuis les `.log.md` accumulés |
| Manuel | Sur invocation | Régénère intégralement tous les fichiers auto |

## Contexte à charger

1. `agents/worker-common.md` — règles communes (lecture du contexte cascade)
2. `agents/summarizer.md` — ce fichier
3. `norms/NORMS.md`
4. `clients/{C}/client.md` + `memory/` — niveau client
5. `clients/{C}/projects/{P}/project.md` + `memory/` — niveau projet (si périmètre projet)
6. Tous les `tasks/RM*.md` du périmètre traité
7. Tous les `tasks/RM*.log.md` du périmètre traité (depuis la dernière exécution)

## Génération de Changelog.md

Format append-only par tâche fermée :

```markdown
## 2026-04-27 — RM1234 : Scraping catalogue produits
**Type :** feature | **Statut final :** ferme (resolu) | **Worker :** worker-dev
**Tokens :** 12 450 | **Temps :** 45 min
{Synthèse en 1-3 phrases du livrable et de l'impact.}
```

Au niveau **client** : agrège les Changelog de tous les projets, condensé.
Au niveau **projet** : entrée détaillée par tâche fermée.

## Génération de Pistes.md

Agrège les `pistes[]` extraites des frontmatters de tâches fermées récemment.
Dédoublonner par `label`. Format :

```markdown
## {label}
**Type :** {type} | **Effort :** {effort}
**Issue de :** RM1234, RM1240
{Description si présente, sinon synthèse depuis les .log.md liés.}
```

## Génération de Remarques.md

Extrait des observations factuelles répétées dans les `.log.md` :
- Patterns détectés (ex: "ce module est touché à chaque sprint")
- Anomalies (ex: "tests régulièrement flaky sur module X")
- Décisions implicites (ex: "convention de nommage Y observée")

Format :

```markdown
## {date} — {résumé en une ligne}
**Source :** RM1234.log.md, RM1238.log.md
{Observation détaillée, factuelle, datée.}
```

## Mise à jour de la section "Structure / Fonctionnement"

Section enrichie progressivement dans `client.md` et `project.md`.
À chaque exécution, le summarizer :
1. Lit la section actuelle
2. Identifie les nouveaux éléments structurels observés (architecture, processus, patterns)
3. Met à jour la section en conservant les éléments toujours pertinents
4. Marque les changements dans le `.log.md` du summarizer (à créer si besoin)

## Mise à jour de memory/

Le summarizer peut créer ou enrichir des fichiers dans `memory/` quand un sujet le mérite :
- `memory/contraintes-techniques.md` — au niveau client si récurrent
- `memory/decisions-architecture.md` — au niveau projet
- `memory/{thématique}.md` — un fichier par thématique structurante

Chaque fichier de memory a son propre frontmatter minimal :

```yaml
---
created: 2026-04-27
updated: 2026-04-27
sources: [RM1234, RM1238]   # tâches qui ont alimenté cette mémoire
---
```

## Règles de neutralité

- Ne jamais inventer d'information : tout doit pouvoir être tracé à un `.log.md` ou un fichier source
- En cas de doute → ne pas écrire, signaler dans le journal d'exécution
- Ne pas effacer ce qui est encore pertinent : remplacer uniquement quand une info est obsolète
- Garder les mises à jour incrémentales — ne pas réécrire intégralement à chaque passage

## Optimistic locking

Mêmes règles que les workers (voir `worker-common.md`) : vérifier `updated` avant chaque écriture.
