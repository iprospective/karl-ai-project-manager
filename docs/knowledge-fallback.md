# Knowledge PM — mode local, snapshot et remote (RM3609)

PM ne doit **jamais dépendre** de `mmi-kb` pour démarrer.

## Modes

| Mode | Source | Besoin |
|---|---|---|
| `local` (défaut) | `<core>/knowledge/*.md` | rien |
| `snapshot` | `<core>/knowledge/kb-snapshot/` | bundle versionné |
| `remote` | `https://kb.iprospective.fr` | réseau + jeton éventuel |

Variables : `PM_KB_MODE`, `PM_KB_LOCAL`, `PM_KB_SNAPSHOT`, `PM_KB_URL`, `PM_KB_TOKEN`.

## Bundle

```text
kb-snapshot/
  manifest.json       # schema, knowledge_commit, generated_at
  entities.jsonl      # une fiche JSON par ligne
  views/<vue>.json    # vues pré-générées
```

Aucun secret, client ou ticket dans le bundle. Le bundle est **read-only** pour PM :
il vient de BK, il ne remplace pas les procédures core PM.

## CLI

```bash
mmi-pm knowledge info
mmi-pm knowledge get doc:redmine/api
mmi-pm knowledge search API
mmi-pm knowledge view docs --tool redmine
```

## Repli

En mode `remote`, une API indisponible ou une fiche absente retombe sur le snapshot
puis sur le local. Une référence manquante est un avertissement, pas un crash.

## Source de vérité

- procédures core PM : PM (`pm_core: true`) ;
- fiches produit génériques : BK (`source_of_truth: kb`) ;
- une copie BK d'une procédure core est `derived_from` et ne doit pas être éditée
  comme source.
