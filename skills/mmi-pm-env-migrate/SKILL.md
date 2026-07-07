---
name: mmi-pm-env-migrate
description: Restructure/normalise un workspace de projet au layout standard RM1993 (bares dans repos/, worktrees dans envs/, racine ne trackant que .mmi-pm/) via l'outil canonique pm-env-migrate (jamais de migration à la main). Couvre aussi les outils frères pm-env-init (instancier/teardown le layout git) et pm-env-session (env de session par ticket). Usage : "/mmi-pm-env-migrate", ou langage naturel "restructure/normalise ce workspace", "migre au layout RM1993", "passe ce projet en repos/ + envs/", "normalise les dossiers envs et repos".
allowed-tools: Bash, Read, Edit, Write
---

# Skill : mmi-pm-env-migrate

Migrer un workspace **pré-norme** (clones de code posés en vrac : `dev/`, `<projet>/`,
copies legacy…) vers le layout standard **RM1993** avec l'outil canonique
`pm-env-migrate` (RM2028). Tripwire #1 des NORMS : **jamais à la main** — l'outil gère
bares, worktrees, sauvegarde des refs, backfill `meta.yml` et `.gitignore`.

## Quand le déclencher

- « restructure / normalise ce workspace (dossiers envs, repos) », « migre au layout
  RM1993 », « passe en repos/ + envs/ », « ce projet est encore au vieux layout »
- Un workspace PM-tracké dont le code n'est **pas** sous `envs/<repo>-<usage>`.
- NE PAS confondre avec `/mmi-env-sync` (rapatrier les données de prod en base locale).

## Le layout cible (RM1993, design figé — détail : ticket RM1993)

```
<workspace>/                    repo -core : ne tracke QUE .mmi-pm/
├── .mmi-pm/                    volet PM co-localisé (meta.yml, project/, tasks/, memory/)
├── repos/<repo>.git            bare(s) — TOUJOURS, même mono-repo
├── envs/                       worktrees <repo>-<usage> :
│   ├── <repo>-dev              défaut (branche d'intégration)
│   ├── <repo>-test             à la demande (main|master)
│   └── <repo>-rm<id>           env de session ticket (pm-env-session, RM1834)
├── tmp/ sessions/ logs/ data/  runtime partagé (créés à la demande)
└── .gitignore                  whitelist : /* sauf .gitignore, .mmi-pm/ (+ AGENTS/CLAUDE.md)
```

Manifeste `.mmi-pm/meta.yml › repos:` : `name`, `remotes:` (`origin` = GitLab,
obligatoire), `integration_branch`, optionnels `implements` et `runtime:`
(pool/docroot/db — consommé par pm-env-session).

## Procédure

Point d'entrée préféré : le CLI **`mmi-pm`** (présent sur les instances privsep —
il re-exécute le script avec le bon user). Fallback : le script du repo PM
(`<repo-pm>/scripts/pm-env-migrate.py` ; repo PM = cible du symlink `.mmi-pm` remontée
à la racine, ex. `/zfs/workspaces/.mmi-pm-core`).

```bash
mmi-pm env migrate <ws> --dry-run -v    # 1. TOUJOURS : lire le plan d'abord
mmi-pm env migrate <ws> -y -v           # 2. migration réelle
# (sans <ws> : découverte depuis le cwd via .mmi-pm)
```

L'outil : détecte les clones du même repo (même remote), crée le bare, adopte chaque
clone en worktree `envs/<repo>-<nom>` (dirty/untracked/ignorés **préservés** par rsync,
refs locales sauvées dans `refs/mig/<nom>/*`), backfill `meta.yml › repos:`, réécrit le
`.gitignore`, puis `fsck` de vérification.

### Snapshot ZFS (réversibilité)

L'outil tente `zfs snapshot` avant mutation. S'il échoue (« droit délégué manquant » —
l'user n'a pas de `zfs allow` et sudo est interactif) :

1. proposer à l'humain de lancer lui-même :
   `! sudo zfs snapshot <pool>/workspaces@pm-env-migrate-<date>` ;
2. ou faire un tar de secours (workspaces souvent petits — vérifier `du -sh` d'abord)
   puis relancer avec `--no-snapshot` :
   `tar -C <parent> -czf <scratchpad>/<ws>-pre-migrate-<date>.tgz <ws>`

## Post-migration (l'outil ne fait PAS ça)

1. **Vérifier** : `git -C envs/<repo>-dev status -sb` (chaque worktree),
   `git -C repos/<repo>.git worktree list`.
2. **`.mmi-pm/project/overview.md`** : section Workspace souvent périmée (ancien chemin
   de code) → documenter racine, bare, worktrees.
3. **`*.code-workspace`** (VS Code) : repointer les `folders.path` vers `envs/…`.
4. **Ménage racine** : ne garder que les dossiers standards ; reliquats legacy → `data/`
   (ou suppression si vide), consigner dans overview.md.
5. **Commit + push** (chemins explicites, jamais `-A`) sur le repo -core, pattern :
   `chore(env-migrate): layout repos/+envs/ — backfill meta.repos + .gitignore norme (RM2028)`

## Outils frères (même famille, ne pas réinventer)

| Besoin | Outil |
|---|---|
| Nouveau workspace / repo ajouté au manifeste → instancier bares+worktrees | `mmi-pm env init` (`--with-test`, `--teardown`, `--purge`) |
| Worktree + runtime d'un ticket (`envs/<repo>-rm<id>`, hooks en_cours/ferme) | `pm-env-session.py create|teardown|list` |
| Rapatrier les données de prod dans la base locale | skill `/mmi-env-sync` |
