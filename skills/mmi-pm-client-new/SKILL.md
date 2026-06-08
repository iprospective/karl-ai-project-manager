---
name: mmi-pm-client-new
description: Crée un nouveau client/produit/self dans l'arbo PM : `clients/<slug>/{client,memory,projects,projects_used}/` + `client/overview.md` rempli depuis template. Ne touche pas à Redmine. Usage : "/mmi-pm-client-new --slug acme --name 'Acme' --type client" ou langage naturel "crée le client acme", "ajoute le produit nextcloud".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-client-new

Wrapper contextuel autour de `scripts/pm-client-new.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "crée le client X", "ajoute le client X"
- "nouveau produit X", "crée le self X"
- `/mmi-pm-client-new --slug X --name "..." --type ...`

## Détection contexte

Détection du projet courant via `cwd` (symlink `mmi-pm` ou `.mmi-pm` ou position dans `<projects_root>/clients/<E>/projects/<P>/`). Pas besoin de demander à l'utilisateur si le contexte est résolvable.

## Invocation

```bash
scripts/pm-client-new.py --slug X --name "X" --type [client|product|self]
```

## Exemples

```bash
# Client tiers commercial
./pm-client-new.py --slug acme --name "Acme Corp" --type client

# Produit (écosystème logiciel)
./pm-client-new.py --slug nextcloud --name "Nextcloud" --type product \
  --gitlab-group iprospective/nextcloud

# Self (projets perso)
./pm-client-new.py --slug lemathou --name "Lemathou" --type self
```

## Notes

Types : `client` (tiers commercial), `product` (écosystème logiciel — redmine, dolibarr, nextcloud…), `self` (interne — iprospective, lemathou). Création projet vient après via `mmi-pm-project-new`.
